"""Wire the approved role engine, exact-model gates and account leases.

Production installs common modules beside this package. Relative imports win.
`common.*` is only the staging tree. A missing account client fails closed.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import importlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

ENGINE = "proposed-2026-10-29"
ACCOUNT_EMAIL = "[account-email-redacted]"
ACCOUNT_ID = hashlib.sha256(ACCOUNT_EMAIL.encode()).hexdigest()


class CapacityUnavailable(RuntimeError):
    """The account coordinator is missing or refused the call."""


def limits_file():
    from .model_limits import LIMITS_FILE
    return Path(LIMITS_FILE)


def account_config_path() -> Path:
    """Production config sits beside model-limits, never next to this source tree."""
    override = os.environ.get("PASEO_ACCOUNT_CAPACITY_CONFIG")
    if override:
        return Path(override)
    return limits_file().parent / "account-capacity.json"


def host_id() -> str:
    value = _raw_account().get("host_id")
    if not isinstance(value, str) or not value.strip():
        raise CapacityUnavailable("host_id missing from account config")
    return value.strip()


def _module(name):
    """Prefer orchestrator/policy_runtime.py; staging may still use common/."""
    try:
        return importlib.import_module(f".{name}", __package__)
    except ImportError:
        pass
    try:
        return importlib.import_module(f"common.{name}")
    except ImportError as error:
        raise CapacityUnavailable(f"{name} unavailable") from error


def runtime():
    try:
        return _module("policy_runtime")
    except CapacityUnavailable as error:
        raise RuntimeError("policy_runtime.evaluate is required") from error


def policy_enabled(limits=None) -> bool:
    if limits is None:
        from .model_limits import load_limits
        try:
            limits = load_limits()
        except (OSError, ValueError):
            return False
    return (limits or {}).get("policy_engine") == ENGINE


def _raw_account() -> dict:
    path = account_config_path()
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    return data if isinstance(data, dict) else {}


def account_config() -> dict:
    data = dict(_raw_account())
    data.setdefault("url", "http://127.0.0.1:6771")
    data.setdefault("token_file", str(limits_file().parent / "account-capacity.token"))
    data.setdefault("account_id", ACCOUNT_ID)
    if not isinstance(data.get("host_id"), str) or not data["host_id"].strip():
        raise CapacityUnavailable("host_id missing from account config")
    for env, key in (("PASEO_CAPACITY_URL", "url"), ("PASEO_CAPACITY_TOKEN_FILE", "token_file")):
        if os.environ.get(env):
            data[key] = os.environ[env]
    return data


def open_client():
    module = _module("account_client")
    client_cls = getattr(module, "Client", None)
    if client_cls is None:
        raise CapacityUnavailable("account_client.Client missing")
    source_error = getattr(module, "CapacityUnavailable", CapacityUnavailable)
    try:
        raw = client_cls(account_config())
    except source_error as error:
        raise CapacityUnavailable(str(error)) from error
    class NormalizedClient:
        def __getattr__(self, name):
            member = getattr(raw, name)
            if not callable(member):
                return member
            def call(*args, **kwargs):
                try:
                    return member(*args, **kwargs)
                except source_error as error:
                    raise CapacityUnavailable(str(error)) from error
            return call
    return NormalizedClient(), CapacityUnavailable


def role_for(task, phase):
    if phase == "review" or (task or {}).get("specialty") == "review" or (task or {}).get("review_role"):
        return "reviewer"
    if (task or {}).get("supervisor_role") or (task or {}).get("specialty") in {"planning", "coordination"}:
        return "manager"
    return "programmer"


def _entry(catalog, provider, model):
    models = catalog.get("models", []) if isinstance(catalog, dict) else catalog or []
    for item in models:
        if isinstance(item, dict) and item.get("provider") == provider and item.get("id") == model:
            return item
    return None


def exact_barriers(entry, now=None):
    """Hard gates for the chosen model only. Concurrency does not select another model."""
    if not isinstance(entry, dict):
        return "catalog_missing"
    if entry.get("authenticated") is not True:
        return "authentication_not_verified"
    if entry.get("available") is not True:
        return "provider_or_model_unavailable_or_unknown"
    quota=entry.get('quota') or {}
    observed=runtime()._timestamp(quota.get('observed_at'))
    if entry.get('provider') not in {'antigravity','antigravity2','antigravity3'}:
        moment=runtime()._moment(now)
        if observed is None or not 0<=moment-observed<=300:return 'quota_observation_stale'
    cost = entry.get("cost") or {}
    additional = cost.get("additional_cost")
    if cost.get("verified") is not True or cost.get("kind") != "subscription" or additional != 0:
        return "zero_additional_cost_not_verified"
    return None


def select_for_role(catalog, task, limits, *, now=None, phase="implement", state=None):
    from .model_limits import allowed_model, astra_allowed

    evaluate = runtime().evaluate
    role = role_for(task or {}, phase)
    decision = evaluate(role, catalog, limits, now=now, state=copy.deepcopy(state) if state is not None else None, implementation_model=(task or {}).get("implementation_model"), review_task=task)
    if not isinstance(decision, dict):
        raise RuntimeError("policy evaluate must return a dict")
    reason = decision.get("reason") or "policy"
    base = {
        "selected": None, "ranking": [], "rejected": [], "reason": reason,
        "preference_reason": reason, "policy_state": decision.get("state"),
        "gpt_only": bool(decision.get("gpt_only")), "evidence": decision.get("evidence"),
        "review_context": __import__("orchestrator.task_risk",fromlist=["review_context"]).review_context(task or {}),
        "review_risk": decision.get("review_risk"),
        "role": role, "preserve_artifact": bool((task or {}).get("preserve_artifact")),
    }
    if decision.get("wait") or not decision.get("model_key"):
        base["rejected"] = [{"key": decision.get("model_key"), "reasons": [reason]}]
        return base
    provider, model = decision.get("provider"), decision.get("model")
    key, effort = decision.get("model_key"), decision.get("thinking_option")
    allowed_efforts = set((limits or {}).get("allowed_thinking_options") or [])
    if effort not in allowed_efforts or effort in {"xhigh", "max", "ultra", "ultracode"}:
        base["reason"] = "effort_forbidden"
        base["rejected"] = [{"key": key, "reasons": ["effort_forbidden"]}]
        return base
    if isinstance(key, str) and "astra" in key.lower():
        if not astra_allowed(role, model, effort):
            base["reason"] = "astra_forbidden"
            base["rejected"] = [{"key": key, "reasons": ["astra_forbidden"]}]
            return base
    elif not allowed_model(provider, model, limits):
        base["reason"] = "explicit_user_model_limit"
        base["rejected"] = [{"key": key, "reasons": ["explicit_user_model_limit"]}]
        return base
    barrier = exact_barriers(_entry(catalog, provider, model),now=now)
    if barrier:
        base["reason"] = barrier
        base["rejected"] = [{"key": key, "reasons": [barrier]}]
        return base
    if provider == "grok":
        from .grok_usage import current_evidence, safe_subscription
        if not safe_subscription(current_evidence(now=now)):
            base["reason"] = "grok_billing_unverified"
            base["rejected"] = [{"key": key, "reasons": ["grok_billing_unverified"]}]
            return base
    selected = {
        "key": key, "provider": provider, "id": model, "thinking_option_id": effort,
        "score": 1, "rank": 1, "reasons": [reason],
    }
    base["selected"] = selected
    base["ranking"] = [selected]
    return base


def migrate_flow(db):
    """Side table for chat identity. jobs keeps its original column count."""
    db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        name TEXT PRIMARY KEY, applied_at REAL NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS role_routes (
        chat_id TEXT NOT NULL, role TEXT NOT NULL, state_json TEXT NOT NULL,
        decision_json TEXT NOT NULL, updated REAL NOT NULL,
        PRIMARY KEY (chat_id, role))""")
    db.execute("""CREATE TABLE IF NOT EXISTS capacity_leases (
        lease_id TEXT PRIMARY KEY, host_id TEXT NOT NULL, chat_id TEXT NOT NULL,
        task_id TEXT NOT NULL, role TEXT NOT NULL, phase TEXT, generation INTEGER,
        request_id TEXT NOT NULL, agent_id TEXT, status TEXT NOT NULL, provider TEXT,
        uncertain INTEGER NOT NULL DEFAULT 0, granted_at REAL NOT NULL,
        released_at REAL, terminal_evidence TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS admission_tickets (
        request_id TEXT PRIMARY KEY, agent_id TEXT UNIQUE, chat_id TEXT NOT NULL,
        role TEXT NOT NULL, provider TEXT, model TEXT, effort TEXT, cwd TEXT,
        ticket_json TEXT NOT NULL, bound_at REAL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS policy_job_chats (
        job_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL)""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    route = "NULL"
    if "supervisor_routes" in tables:
        route = """(SELECT primary_id FROM supervisor_routes WHERE
            jobs.supervisor_id IN (primary_id,active_id,fallback_id) AND state!='superseded'
            ORDER BY updated DESC LIMIT 1)"""
    explicit = "jobs.chat_id," if "chat_id" in columns else ""
    db.execute(f"""INSERT OR IGNORE INTO policy_job_chats(job_id, chat_id)
        SELECT jobs.id, COALESCE({explicit}{route},jobs.supervisor_id,jobs.id) FROM jobs""")
    db.execute("INSERT OR IGNORE INTO schema_migrations(name, applied_at) VALUES('policy_job_chats_v1', ?)", (time.time(),))


def _chat_expr(db):
    columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    if "chat_id" in columns:
        return "COALESCE(policy_job_chats.chat_id, jobs.chat_id, jobs.supervisor_id, jobs.id)"
    return "COALESCE(policy_job_chats.chat_id, jobs.supervisor_id, jobs.id)"


def record_job_chat(db, job_id, chat_id):
    migrate_flow(db)
    given = str(chat_id or job_id)
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "supervisor_routes" in tables:
        route = db.execute("""SELECT primary_id FROM supervisor_routes WHERE
            ? IN (primary_id,active_id,fallback_id) AND state!='superseded' ORDER BY updated DESC LIMIT 1""", (given,)).fetchone()
        if route:
            previous = db.execute("SELECT chat_id FROM policy_job_chats WHERE job_id=?", (str(job_id),)).fetchone()
            job = db.execute("SELECT supervisor_id FROM jobs WHERE id=?", (str(job_id),)).fetchone()
            inferred = {given,str(job_id),route["primary_id"],job["supervisor_id"] if job else None}
            given = previous["chat_id"] if previous and previous["chat_id"] not in inferred else route["primary_id"]
    db.execute("""INSERT INTO policy_job_chats(job_id, chat_id) VALUES(?,?)
        ON CONFLICT(job_id) DO UPDATE SET chat_id=excluded.chat_id""", (str(job_id), given))


def chat_of(db, task):
    migrate_flow(db)
    job_id = _field(task, "job_id") or _field(task, "id")
    row = db.execute(
        f"SELECT {_chat_expr(db)} AS chat_id FROM jobs LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id WHERE jobs.id=?",
        (job_id,),
    ).fetchone()
    if not row or row["chat_id"] is None:
        return str(_field(task, "chat_id") or job_id or "unscoped")
    return str(row["chat_id"])


def load_state(db, chat_id, role):
    migrate_flow(db)
    row = db.execute("SELECT state_json FROM role_routes WHERE chat_id=? AND role=?", (chat_id, role)).fetchone()
    return json.loads(row["state_json"]) if row else None


def save_state(db, chat_id, role, state, decision):
    migrate_flow(db)
    db.execute("""INSERT INTO role_routes(chat_id, role, state_json, decision_json, updated)
        VALUES(?,?,?,?,?) ON CONFLICT(chat_id, role) DO UPDATE SET
        state_json=excluded.state_json, decision_json=excluded.decision_json, updated=excluded.updated""",
               (chat_id, role, json.dumps(state or {}), json.dumps(decision or {}), time.time()))


def absorb_global(local, catalog, limits, *, now=None):
    """Broker observations replace local facts. Chat decisions stay on the local state."""
    base = copy.deepcopy(local) if isinstance(local, dict) else {}
    viewed = None
    try:
        client, _unavailable = open_client()
        viewed = client.observe(catalog or {}, limits or {})
    except (CapacityUnavailable, OSError, TimeoutError) as error:
        from .core import ModelUnavailable
        # Preserve the last authenticated state. Exact launch admission still
        # requires the broker, except the explicitly local dedicated accounts.
        base['coordinator_unavailable']=str(error)
        remote=None
        viewed={}

    remote = viewed.get("state") if isinstance(viewed, dict) else None
    cache=limits_file().parent.parent/'orchestration/coordinator-state.json'
    if isinstance(remote,dict):
        temporary=cache.with_name(cache.name+'.'+uuid.uuid4().hex+'.tmp')
        temporary.write_text(json.dumps(remote));temporary.chmod(0o600);temporary.replace(cache)
    elif cache.exists():
        try:remote=json.loads(cache.read_text())
        except (OSError,ValueError):remote=None
    if isinstance(remote, dict):
        base=runtime()._blank_state(base)
        for provider,record in (remote.get('observations') or {}).items():
            if provider in runtime().PROVIDERS and isinstance(record,dict):runtime()._accept(base,provider,record.get('status'),record.get('observed_at'),record.get('reason'))
    absorbed = runtime().absorb_catalog(base, catalog or {}, limits or {}, now=now)
    state = absorbed["state"]
    if isinstance(local, dict) and isinstance(local.get("decisions"), dict):
        state["decisions"] = copy.deepcopy(local["decisions"])
    return state


def attach_policy_state(db, task, query, catalog=None):
    if not policy_enabled():
        return query
    from .model_limits import load_limits
    chat_id = chat_of(db, task)
    role = role_for(query, task.get("phase") or "implement")
    query["chat_id"] = chat_id
    query["policy_state"] = absorb_global(load_state(db, chat_id, role), catalog, load_limits())
    if str(task.get("error") or "").startswith(("programmer_quota", "maintenance_resume")):
        query["preserve_artifact"] = True
    return query


def store_policy_state(db, task, result):
    if not policy_enabled() or not isinstance(result, dict) or "policy_state" not in result:
        return
    chat_id = result.get("role") and chat_of(db, task)
    if not chat_id:
        return
    decision = {
        "reason": result.get("reason"), "model": (result.get("selected") or {}).get("key"),
        "selected": result.get("selected"), "gpt_only": result.get("gpt_only"),
        "model_key": (result.get("selected") or {}).get("key"),
        "thinking_option": (result.get("selected") or {}).get("thinking_option_id"),
    }
    save_state(db, chat_id, result.get("role"), result.get("policy_state"), decision)
    publish_decision(chat_id, result.get("role"), {**result, **decision})


TICKET_FIELDS = ("agent_id", "chat_id", "cwd", "decision_fp", "effort", "model", "provider", "request_id", "role", "v")


def decision_fingerprint(decision):
    selected = (decision or {}).get("selected") or {}
    body = {
        "effort": selected.get("thinking_option_id") or (decision or {}).get("thinking_option"),
        "gpt_only": bool((decision or {}).get("gpt_only")),
        "model": selected.get("key") or (decision or {}).get("model_key"),
        "reason": (decision or {}).get("reason"),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sign_ticket(body, token):
    payload = {key: body.get(key) for key in TICKET_FIELDS}
    payload["v"] = 1
    mac = hmac.new(token.encode(), json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
    return {**payload, "mac": mac}


def verify_ticket(ticket, token):
    if not isinstance(ticket, dict) or not ticket.get("mac"):
        return False
    expected = sign_ticket(ticket, token)
    return hmac.compare_digest(str(ticket.get("mac")), expected["mac"])


def _token():
    path = Path(account_config()["token_file"])
    if not path.is_file():
        raise CapacityUnavailable("capacity token file missing")
    return path.read_text().strip()


def _field(row, name, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(name, default)
    try:
        value = row[name]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _generation_for(db, task_id, role, attempt, provider=None, model=None, effort=None):
    """Uncertain/held work keeps its generation. A new model or a release may advance it."""
    suffix = f"-{provider}-{model}-{effort}" if provider and model else None
    try:
        rows = db.execute(
            "SELECT generation, status, request_id FROM capacity_leases WHERE task_id=? AND role=?",
            (task_id, role),
        ).fetchall()
    except sqlite3.Error:
        rows = []
    for row in rows:
        if row["status"] in {"held", "uncertain"} and (suffix is None or str(row["request_id"] or "").endswith(suffix)):
            return int(row["generation"])
    if suffix and any(row["status"] in {"held", "uncertain"} for row in rows):
        return max(int(row["generation"] or 0) for row in rows) + 1
    previous = max((int(row["generation"] or 0) for row in rows if row["status"] == "released"), default=0)
    base = max(int(attempt or 0), 1)
    return max(base, previous + 1) if previous else base


def _task_ready(db, row, now):
    if row["jobs_state"] != "running" or row["state"] != "queued":
        return False
    if row["retry_at"] and now < float(row["retry_at"]):
        return False
    if row["phase"] not in {"implement", "review"}:
        return False
    spec = json.loads(row["spec"]) if row["spec"] else {}
    deps = spec.get("depends_on") or []
    if deps:
        states = {
            item["task_key"]: item["state"]
            for item in db.execute("SELECT task_key, state FROM tasks WHERE job_id=?", (row["job_id"],))
        }
        if any(states.get(dep) != "done" for dep in deps):
            return False
    return True


def _ready_by_chat(db, now=None):
    """Ready programmer/reviewer work only. Paused plans, future retries and open deps stay out."""
    migrate_flow(db)
    moment = time.time() if now is None else now
    chat_sql = _chat_expr(db)
    rows = db.execute(f"""SELECT tasks.id, tasks.phase, tasks.attempt, tasks.state, tasks.retry_at, tasks.spec,
        tasks.job_id, jobs.state AS jobs_state, {chat_sql} AS chat_id
        FROM tasks JOIN jobs ON jobs.id=tasks.job_id
        LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id
        WHERE jobs.state NOT IN ('canceled','cancelled')""").fetchall()
    grouped = {}
    for row in rows:
        chat = str(row["chat_id"] or row["job_id"])
        grouped.setdefault(chat, [])
        if not _task_ready(db, row, moment):
            continue
        role = "reviewer" if row["phase"] == "review" else "programmer"
        generation = _generation_for(db, row["id"], role, row["attempt"])
        grouped[chat].append({
            "task_id": str(row["id"]),
            "role": role,
            "request_id": f"flow-{row['id']}-{row['phase']}-{generation}",
            "generation": generation,
            "phase": row["phase"],
        })
    return grouped


def register_ready_chats(client, db, now=None):
    grouped = _ready_by_chat(db, now=now)
    for chat_id, candidates in grouped.items():
        client.register(str(chat_id), candidates, replace=True)
    return grouped


def _remember_lease(db, lease_id, chat_id, task, role, phase, generation, request_id, agent_id, provider):
    """Keep a granted lease when the broker decision blocks the launch."""
    migrate_flow(db)
    db.execute("""INSERT OR REPLACE INTO capacity_leases(lease_id, host_id, chat_id, task_id, role, phase, generation, request_id,
        agent_id, status, provider, uncertain, granted_at) VALUES(?,?,?,?,?,?,?,?,?, 'held', ?, 0, ?)""",
               (lease_id, host_id(), str(chat_id), task["id"], role, phase, generation, request_id, agent_id, provider, time.time()))
    db.commit()


def prepare_native_launch(db, task, job, selection, options):
    from .operator_hold import require_running
    require_running()
    """Lease and ticket before the native create. Missing client does not pretend success."""
    if not policy_enabled():
        return "agent-create", options
    role = (selection or {}).get("role") or role_for(task, _field(task, "phase"))
    chat_id = _field(job, "chat_id") or chat_of(db, task)
    provider = options.get("provider")
    model = options.get("model")
    effort = options.get("thinkingOptionId")
    if isinstance(model, str) and "astra" in model.lower():
        if role != "manager" or effort != "medium" or provider != "codex":
            from .core import ModelUnavailable
            raise ModelUnavailable("astra_forbidden")
    migrate_flow(db)
    retry_pending_releases(db)
    old = db.execute("SELECT role,status,terminal_evidence FROM capacity_leases WHERE task_id=? AND status!='released'",(task["id"],)).fetchall()
    for row in old:
        terminal = json.loads(row["terminal_evidence"] or "{}")
        if (row["status"] == "release_pending" and row["role"] == role) or terminal.get("kind") == "archive_unconfirmed":
            from .core import ModelUnavailable
            raise ModelUnavailable("terminal_release_wait")
    generation = _generation_for(db, task["id"], role, _field(task, "attempt"), provider, model, effort) if role in {"programmer", "reviewer"} else max(int(_field(task, "attempt") or 1), 1)
    request_id = str(options.get("idempotencyKey") or f"flow-{task['id']}-{role}")
    suffix = f"-{provider}-{model}-{effort}"
    expected_key = f"{provider}/{model}"
    held = None
    if role in {"programmer", "reviewer"}:
        held = db.execute("""SELECT lease_id, generation, request_id, agent_id FROM capacity_leases
            WHERE task_id=? AND role=? AND generation=? AND status IN ('held','uncertain')
            ORDER BY granted_at DESC LIMIT 1""", (task["id"], role, generation)).fetchone()
    if held and held["request_id"]:
        request_id = held["request_id"]
        pre_agent = held["agent_id"] or options.get("agentId") or str(uuid.uuid4())
    else:
        base_request = request_id.split(suffix)[0] if suffix and suffix in request_id else request_id
        request_id = f"{base_request}-g{int(generation)}{suffix}"
        pre_agent = options.get("agentId") or str(uuid.uuid4())
    previous = db.execute("SELECT agent_id FROM admission_tickets WHERE request_id=?", (request_id,)).fetchone()
    if previous and previous["agent_id"] and not options.get("agentId"):
        pre_agent = previous["agent_id"]
    options = {**options, "idempotencyKey": request_id, "agentId": pre_agent}
    needs_lease = role in {"programmer", "reviewer"}
    lease_id = held["lease_id"] if held else None
    # Recovery may occupy only one slot for the exhausted Gemini account.
    selected_evidence=(selection or {}).get('evidence') or {}
    if (selected_evidence.get(runtime().quota_key(expected_key)) or {}).get('status')=='recovery_due':
        other=db.execute("SELECT 1 FROM capacity_leases WHERE provider=? AND task_id<>? AND status!='released'",(provider,task['id'])).fetchone()
        if other:
            from .core import ModelUnavailable
            raise ModelUnavailable('quota_recovery_in_progress')
    if needs_lease:
        try:
            client, unavailable = open_client()
            client.status()
        except CapacityUnavailable as error:
            from .core import ModelUnavailable
            from .local_capacity import local_client
            client=local_client(db,provider)
            if client is None:raise ModelUnavailable('Coordenador indisponível; conta compartilhada preservada: '+str(error)) from error
            unavailable=CapacityUnavailable
        try:
            grouped = register_ready_chats(client, db)
            phase = _field(task, "phase") or ("review" if role == "reviewer" else "implement")
            grant = client.acquire(str(chat_id), str(task["id"]), role, request_id, {
                "generation": int(generation),
                "phase": phase,
                "implementation_model": _field(task, "model") if role == "reviewer" else None,
                "review_context": (selection or {}).get("review_context") if role == "reviewer" else None,
                "adopt_existing": False,
                "requested_model_key": expected_key,
                "requested_thinking_option": effort,
                "model_key": expected_key,
                "thinking_option": effort,
                "agent_id": pre_agent,
                "ready_candidates": grouped.get(str(chat_id), []),
            })
            matched = isinstance(grant, dict) and grant.get("granted") and grant.get("model_key") == expected_key and grant.get("thinking_option") == effort
            if not matched:
                if isinstance(grant, dict) and grant.get("granted") and grant.get("lease_id"):
                    _remember_lease(db, grant["lease_id"], chat_id, task, role, phase, generation, request_id, pre_agent, provider)
                from .core import ModelUnavailable
                raise ModelUnavailable((grant or {}).get("reason") or "policy_decision_diverged")
            lease_id = grant["lease_id"]
            _remember_lease(db,lease_id,chat_id,task,role,phase,generation,request_id,pre_agent,provider)
            db.commit()
            bound = client.bind(lease_id, pre_agent)
            if not isinstance(bound, dict) or not bound.get("bound"):
                _remember_lease(db, lease_id, chat_id, task, role, phase, generation, request_id, pre_agent, provider)
                from .core import ModelUnavailable
                raise ModelUnavailable((bound or {}).get("reason") or "bind_failed")
        except (unavailable, CapacityUnavailable, AttributeError) as error:
            from .core import ModelUnavailable
            raise ModelUnavailable(str(error)) from error
        except (TimeoutError, OSError) as error:
            from .core import ModelUnavailable
            raise ModelUnavailable("capacity_transport:" + str(error)) from error
    token = _token()
    fingerprint = decision_fingerprint(selection or {"role": role, "selected": {"key": f"{provider}/{model}", "thinking_option_id": effort}, "reason": (selection or {}).get("reason")})
    publish_decision(str(chat_id), role, selection or {"reason": role, "selected": {"key": f"{provider}/{model}", "thinking_option_id": effort}})
    ticket = sign_ticket({
        "v": 1, "role": role, "provider": provider, "model": model, "effort": effort,
        "request_id": request_id, "cwd": options.get("cwd") or "", "chat_id": str(chat_id),
        "agent_id": pre_agent, "decision_fp": fingerprint,
    }, token)
    migrate_flow(db)
    db.execute("""INSERT OR REPLACE INTO admission_tickets(request_id, agent_id, chat_id, role, provider, model, effort, cwd, ticket_json, bound_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
               (request_id, pre_agent, str(chat_id), role, provider, model, effort, options.get("cwd"), json.dumps(ticket), time.time()))
    if lease_id:
        db.execute("""INSERT OR REPLACE INTO capacity_leases(lease_id, host_id, chat_id, task_id, role, phase, generation, request_id,
            agent_id, status, provider, uncertain, granted_at) VALUES(?,?,?,?,?,?,?,?,?, 'held', ?, 0, ?)""",
                   (lease_id, host_id(), str(chat_id), task["id"], role, _field(task, "phase"), generation, request_id, pre_agent, provider, time.time()))
    labels = dict(options.get("labels") or {})
    labels.update({
        "flow.chat": str(chat_id), "flow.provider": str(provider), "flow.role": role,
        "flow.lease": lease_id or "", "flow.session": _field(task, "phase") or role,
        "trustedController": "1", "flow.request": request_id,
    })
    if isinstance(model, str) and "astra" in model.lower():
        labels["flow.astra"] = "temporary"
    env = dict(options.get("env") or {})
    env.update({
        "PASEO_ROLE_TICKET": json.dumps(ticket, separators=(",", ":")),
        "PASEO_ADMISSION_DB": str(_admission_db()),
        "PASEO_FLOW_CHAT": str(chat_id), "PASEO_FLOW_ROLE": role,
        "PASEO_FLOW_PROVIDER": str(provider),
        "PASEO_FLOW_LEASE": lease_id or "", "PASEO_TRUSTED_CONTROLLER": "1",
        "PASEO_CAPACITY_TOKEN_FILE": account_config()["token_file"],
        "PASEO_MODEL_LIMITS": str(limits_file()),
        "PASEO_ACCOUNT_CAPACITY_CONFIG": str(account_config_path()),
        "PASEO_FLOW_DB": str(_flow_db()),
        "PASEO_ACTIVE_CHATS": str(max(int(db.execute("SELECT COUNT(DISTINCT chat_id) FROM policy_job_chats").fetchone()[0] or 1), 1)),
        "GROK_REASONING_EFFORT": effort or "",
    })
    _mirror_ticket(_admission_db(), pre_agent, ticket)
    options = {**options, "labels": labels, "env": env, "agentId": pre_agent, "admissionTicket": ticket}
    return "staged-launch", options


def _admission_db():
    from . import core
    return Path(os.environ.get("PASEO_ADMISSION_DB", core.STATE / "admission.sqlite3"))


def _flow_db():
    from . import core
    return Path(os.environ.get("PASEO_FLOW_DB", core.STATE / "state.sqlite3"))


def publish_decision(chat_id, role, decision):
    fingerprint = decision_fingerprint(decision or {})
    _mirror_decision(_admission_db(), str(chat_id), str(role), fingerprint)
    return fingerprint


def _mirror_decision(path, chat_id, role, fingerprint):
    import sqlite3
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS current_decisions (
        chat_id TEXT NOT NULL, role TEXT NOT NULL, fingerprint TEXT NOT NULL, updated REAL NOT NULL,
        PRIMARY KEY (chat_id, role))""")
    db.execute("""INSERT INTO current_decisions(chat_id, role, fingerprint, updated) VALUES(?,?,?,?)
        ON CONFLICT(chat_id, role) DO UPDATE SET fingerprint=excluded.fingerprint, updated=excluded.updated""",
               (chat_id, role, fingerprint, time.time()))
    db.commit()
    db.close()


def _mirror_ticket(path, agent_id, ticket):
    import sqlite3
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS tickets (
        agent_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, role TEXT, provider TEXT, model TEXT,
        effort TEXT, cwd TEXT, chat_id TEXT, mac TEXT, ticket_json TEXT NOT NULL)""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(tickets)")}
    for name, declaration in {"provider": "TEXT", "chat_id": "TEXT", "ticket_json": "TEXT"}.items():
        if name not in columns:
            db.execute(f"ALTER TABLE tickets ADD COLUMN {name} {declaration}")
    db.execute("""INSERT OR REPLACE INTO tickets(agent_id, request_id, role, provider, model, effort, cwd, chat_id, mac, ticket_json)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
               (agent_id, ticket["request_id"], ticket["role"], ticket.get("provider"), ticket["model"], ticket["effort"],
                ticket["cwd"], ticket.get("chat_id"), ticket["mac"], json.dumps(ticket, separators=(",", ":"))))
    db.commit()
    db.close()


def bind_launched(db, task, agent_id):
    if not policy_enabled():
        return
    migrate_flow(db)
    row = db.execute("""SELECT lease_id, request_id, agent_id FROM capacity_leases
        WHERE task_id=? AND status IN ('held','uncertain') ORDER BY granted_at DESC LIMIT 1""", (task["id"],)).fetchone()
    if not row:
        return
    bound = agent_id or row["agent_id"]
    db.execute("UPDATE capacity_leases SET agent_id=? WHERE lease_id=?", (bound, row["lease_id"]))
    db.execute("UPDATE admission_tickets SET agent_id=? WHERE request_id=?", (bound, row["request_id"]))
    client, unavailable = open_client()
    try:
        client.bind(row["lease_id"], bound)
    except unavailable:
        db.execute("UPDATE capacity_leases SET status='uncertain', uncertain=1 WHERE lease_id=?", (row["lease_id"],))


def mark_uncertain(db, task):
    if not policy_enabled():
        return
    migrate_flow(db)
    row = db.execute("""SELECT lease_id FROM capacity_leases WHERE task_id=? AND status IN ('held','uncertain')
        ORDER BY granted_at DESC LIMIT 1""", (task["id"],)).fetchone()
    if not row:
        return
    db.execute("UPDATE capacity_leases SET status='uncertain', uncertain=1 WHERE lease_id=?", (row["lease_id"],))
    try:
        client, _unavailable = open_client()
        if hasattr(client, "uncertain"):
            client.uncertain(row["lease_id"])
    except CapacityUnavailable:
        pass


def retry_pending_releases(db):
    """Replay only durable known terminal proofs, including after a restart."""
    if not policy_enabled():
        return
    migrate_flow(db)
    rows = db.execute("SELECT lease_id,agent_id,request_id,terminal_evidence FROM capacity_leases WHERE status='release_pending'").fetchall()
    if not rows:
        return
    try:
        client, _ = open_client()
        for row in rows:
            proof = json.loads(row["terminal_evidence"] or "{}")
            if (proof.get("kind") not in {"completed","cancelled"} or proof.get("agent_id") != row["agent_id"]
                    or proof.get("request_id") != row["request_id"]):
                continue
            if str(row['lease_id']).startswith('local-'):
                db.execute("UPDATE capacity_leases SET status='released',uncertain=0,released_at=? WHERE lease_id=?",(time.time(),row['lease_id']))
                continue
            try:
                result = client.release(row["lease_id"], proof)
            except (CapacityUnavailable,OSError,TimeoutError):
                continue
            if isinstance(result,dict) and result.get("released") and result.get("reason") in {"released","already_released"}:
                db.execute("UPDATE capacity_leases SET status='released',uncertain=0,released_at=? WHERE lease_id=? AND status='release_pending'",(time.time(),row["lease_id"]))
    except (CapacityUnavailable,OSError,TimeoutError):
        pass
    db.commit()


def release_task(db, task, evidence):
    if not policy_enabled():
        return
    migrate_flow(db)
    agent = _field(task,"agent_id")
    if not agent:
        return
    rows = db.execute("SELECT lease_id,agent_id,request_id,status FROM capacity_leases WHERE task_id=? AND agent_id=? AND status!='released'",(task["id"],agent)).fetchall()
    proof = dict(evidence) if isinstance(evidence,dict) else {"kind":evidence}
    if proof.get("kind") == "canceled":
        proof["kind"] = "cancelled"
    known = proof.get("kind") in {"completed","cancelled"}
    if proof.get("archive_ack") is not None:
        ack = proof["archive_ack"]
        known = known and isinstance(ack,dict) and ack.get("agent_id") == agent and bool(ack.get("archivedAt"))
    for row in rows:
        if row["status"] == "release_pending":
            continue  # A later timeout never discards a previously established proof.
        record = {**proof,"agent_id":agent,"request_id":row["request_id"]}
        if not known:
            record["kind"] = "archive_unconfirmed"
        db.execute("UPDATE capacity_leases SET status=?,uncertain=?,terminal_evidence=? WHERE lease_id=?",
                   ('release_pending' if known else 'uncertain',0 if known else 1,json.dumps(record),row["lease_id"]))
    # Commit the proof before making an external call or advancing the task.
    db.commit()
    retry_pending_releases(db)


def adopt_running_gpt(db):
    """Count Codex workers that already run. Do not stop them if the cap is full."""
    if not policy_enabled():
        return {"adopted": 0}
    migrate_flow(db)
    chat_sql = _chat_expr(db)
    rows = db.execute(f"""SELECT tasks.*, {chat_sql} AS chat_id FROM tasks JOIN jobs ON jobs.id=tasks.job_id
        LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id
        WHERE tasks.state IN ('running','launching','waiting_permission')
        AND ((tasks.phase='review' AND tasks.review_model LIKE 'codex/%')
             OR (tasks.phase!='review' AND tasks.model LIKE 'codex/%'))""").fetchall()
    adopted = 0
    try:
        client, unavailable = open_client()
    except CapacityUnavailable:
        return {"adopted": 0, "coordinator": "unavailable"}
    for task in rows:
        existing = db.execute("SELECT lease_id, status FROM capacity_leases WHERE task_id=? AND status!='released'", (task["id"],)).fetchone()
        if existing:
            continue
        request_id = f"adopt-{task['id']}-{task['phase']}"
        try:
            model_key = task["review_model"] if task["phase"] == "review" else task["model"]
            if not isinstance(model_key, str) or not model_key.startswith("codex/"):
                continue
            role_name = "reviewer" if task["phase"] == "review" else "programmer"
            generation = _generation_for(db, task["id"], role_name, task["attempt"])
            grant = client.acquire(str(task["chat_id"] or task["job_id"]), str(task["id"]), role_name,
                                   request_id, {
                                       "generation": generation, "phase": task["phase"],
                                       "adopt_existing": True, "model_key": model_key,
                                       "agent_id": task["agent_id"],
                                   })
        except unavailable:
            continue
        if not grant.get("granted"):
            continue
        db.execute("""INSERT OR REPLACE INTO capacity_leases(lease_id, host_id, chat_id, task_id, role, phase, generation, request_id,
            agent_id, status, provider, uncertain, granted_at) VALUES(?,?,?,?,?,?,?,?,?, 'held', 'codex', 0, ?)""",
                   (grant["lease_id"], host_id(), str(task["chat_id"] or task["job_id"]), task["id"],
                    "reviewer" if task["phase"] == "review" else "programmer", task["phase"], int(task["attempt"] or 0),
                    request_id, task["agent_id"], time.time()))
        if task["agent_id"]:
            try:
                client.bind(grant["lease_id"], task["agent_id"])
            except unavailable:
                db.execute("UPDATE capacity_leases SET status='uncertain', uncertain=1 WHERE lease_id=?", (grant["lease_id"],))
        adopted += 1
    return {"adopted": adopted}


def _publish_exhaustion(provider, observed_at, message="quota exhausted"):
    """Push one declared quota fact to the shared account. No catalog poll required."""
    model_key = provider
    provider = provider.split("/",1)[0]
    ident = "claude-sonnet-5-5-medium" if model_key == runtime().ANTIGRAVITY_SONNET_KEY else {"codex-programmer": "gpt-6.1-terra", "codex": "gpt-6.1-sol", "claude": "claude-sonnet-5-5", "grok": "grok-4.7", "antigravity": "gemini-3.8-flash-high", "antigravity3": "gemini-3.8-flash-high", "antigravity2": "gemini-3.8-flash-high"}.get(provider)
    if not ident:
        return
    try:
        client, _unavailable = open_client()
        from .model_limits import load_limits
        client.observe({"models": [{
            "provider": provider, "id": ident, "authenticated": True, "available": True,
            "cost": {"verified": True, "additional_cost": 0, "kind": "subscription"},
            "quota": {"source": "official-usage", "observed_at": observed_at, "status": "exhausted", "message":message,
                      "windows": [{"remaining_fraction": 0, "status": "exhausted"}]},
        }]}, load_limits())
    except (CapacityUnavailable, OSError, TimeoutError) as error:
        from .core import ModelUnavailable
        raise ModelUnavailable("capacity_publish:" + str(error)) from error


def record_role_exhaustion(db, task, role, message):
    """Record the provider that actually failed and publish it for the other host."""
    module = runtime()
    if not module.explicit_quota_text(message):
        return None
    failed = _field(task, "review_model") if role == "reviewer" else _field(task, "model")
    if not isinstance(failed, str) or "/" not in failed:
        raw = _field(task, "selection")
        try:
            selected = json.loads(raw).get("selected") if isinstance(raw, str) and raw else {}
        except json.JSONDecodeError:
            selected = {}
        failed = (selected or {}).get("key")
        if not failed and (selected or {}).get("provider") and (selected or {}).get("id"):
            failed = f"{selected['provider']}/{selected['id']}"
    if not isinstance(failed, str) or "/" not in failed:
        return None
    provider = failed.split("/", 1)[0]
    if provider not in {"codex-programmer", "codex", "claude", "grok", "antigravity", "antigravity2", "antigravity3"}:
        return None
    chat_id = chat_of(db, task)
    moment = time.time()
    evidence_key = module.quota_key(failed)
    state = module.note_exhaustion(load_state(db, chat_id, role), evidence_key, moment, message)
    save_state(db, chat_id, role, state, {"reason": "explicit_quota", "provider": provider, "model_key": failed})
    try:_publish_exhaustion(evidence_key,moment,message)
    except Exception as error:
        from . import core
        db.execute("CREATE TABLE IF NOT EXISTS pending_quota_publications(provider TEXT PRIMARY KEY,at REAL NOT NULL,message TEXT)")
        db.execute('INSERT OR REPLACE INTO pending_quota_publications VALUES(?,?,?)',(evidence_key,moment,message))
        core.event(db,'quota_publication_deferred',{'provider':provider,'error':str(error)[-300:]},_field(task,'job_id'),_field(task,'id'))
    return provider


def programmer_quota_handoff(db, task, snapshot):
    from .model_limits import load_limits
    limits = load_limits()
    if not policy_enabled(limits) or _field(task, "phase") != "implement":
        return False
    if not (limits.get("programming") or {}).get("fallback_allowed"):
        return False
    message = str(_field(snapshot, "lastError") or _field(snapshot, "error") or "")
    provider = record_role_exhaustion(db, task, "programmer", message)
    if not provider:
        return False
    from . import core
    if _field(task, "agent_id"):
        proof = core.archive_worker(db, task)
        if not proof:
            core.event(db,"quota_handoff_archive_wait",{"provider":provider},_field(task,"job_id"),_field(task,"id"))
            db.commit()
            return True
        release_task(db,task,{"kind":"cancelled","archive_ack":proof})
    now = core.now()
    waiting = provider == "codex"
    db.execute("""UPDATE tasks SET state='queued', phase='implement',
        previous_agent_id=COALESCE(?, previous_agent_id), agent_id=NULL, launch_request=NULL,
        error=?, retry_at=?, updated=? WHERE id=?""",
               (_field(task, "agent_id"), ("programmer_quota_wait:" if waiting else "programmer_quota:") + message[:400],
                (now + 60) if waiting else None, now, _field(task, "id")))
    core.event(db, "programmer_quota_wait" if waiting else "programmer_quota_fallback", {
        "attempt": _field(task, "attempt"), "preserved_artifact": True, "preserved_attempt": True,
        "from_model": _field(task, "model"), "provider": provider, "reason": message[:500],
    }, _field(task, "job_id"), _field(task, "id"))
    db.commit()
    return True


def resource_config(db):
    if not policy_enabled():
        return None
    chat_sql = _chat_expr(db)
    rows = db.execute(f"""SELECT {chat_sql} AS chat_id FROM jobs
        LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id
        WHERE jobs.state NOT IN ('canceled','cancelled')""").fetchall()
    chats = {row["chat_id"] for row in rows if row["chat_id"]}
    from .model_limits import load_limits
    from .resources import host_envelope
    per = int(load_limits().get("workers_per_chat") or 10)
    return host_envelope(len(chats) or 1, per, 1)


def reserve_manager(db, chat_id, active_id):
    db.execute("CREATE TABLE IF NOT EXISTS manager_owners(chat_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL)")
    db.execute("INSERT INTO manager_owners VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET agent_id=excluded.agent_id",
               (str(chat_id), active_id))


def single_manager(db, chat_id, active_id):
    """Leave one active manager. Paused and canceled jobs stay with their owner."""
    migrate_flow(db)
    reserve_manager(db, chat_id, active_id)
    expr = _chat_expr(db)
    db.execute(f"""UPDATE jobs SET supervisor_id=?, updated=?
        WHERE id IN (
            SELECT jobs.id FROM jobs LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id
            WHERE {expr}=?
        ) AND state NOT IN ('paused','canceled','cancelled') AND supervisor_id IS NOT ?""",
               (active_id, time.time(), str(chat_id), active_id))


def chat_worker_blocked(rows, job, limit, db=None):
    """Reviewers count. Managers are not rows in the task table."""
    chat = chat_of(db, job) if db is not None else None
    if not chat:
        chat = _field(job, "chat_id") or _field(job, "supervisor_id") or _field(job, "id")
    count = 0
    for row in rows:
        if _field(row, "state") not in {"running", "launching", "waiting_permission"}:
            continue
        row_chat = _field(row, "chat_id") or (chat_of(db, row) if db is not None else None) or _field(row, "supervisor_id") or _field(row, "job_id")
        if row_chat == chat:
            count += 1
    return count >= int(limit)


def manager_launch_options(db, chat_id, cwd, prompt, idempotency_key, decision):
    from .operator_hold import require_running
    require_running()
    """Ticketed manager create. Astra stays off the global allowlist."""
    from .model_limits import load_limits, role_summary
    from .supervisor import INSTRUCTIONS, management_title
    selected = decision["selected"]
    limits = load_limits()
    effort = selected["thinking_option_id"]
    provider, model = selected["provider"], selected["id"]
    primary = (limits.get("supervision") or {}).get("primary_model")
    role_label = "primary" if f"{provider}/{model}" == primary else "temporary"
    title = management_title(cwd, role_label != "primary", f"{provider}/{model}", effort)
    mode = {"claude": "bypassPermissions", "codex": "full-access"}.get(provider, "acceptEdits")
    options = {
        "provider": provider, "model": model, "thinkingOptionId": effort, "modeId": mode,
        "cwd": str(cwd), "title": title,
        "systemPrompt": role_summary(limits) + "\n\n" + INSTRUCTIONS, "initialPrompt": prompt,
        "labels": {
            "flow.role": "supervisor", "flow.supervisor.role": role_label,
            "flow.supervisor.thinking": effort, "flow.chat": str(chat_id),
            "trustedController": "1",
        },
        "idempotencyKey": idempotency_key,
    }
    if provider == "grok":
        options.pop("modeId", None)
    task = {"id": idempotency_key, "job_id": chat_id, "phase": "planning", "attempt": 0, "supervisor_role": True}
    job = {"id": chat_id, "chat_id": chat_id}
    action, options = prepare_native_launch(db, task, job, decision, options)
    reserve_manager(db, str(chat_id), options["agentId"])
    return action, options


def ensure_current_manager_ticket(db, chat_id, current, decision):
    """Admit an existing trusted route at an idle boundary, without SDK calls."""
    from . import core
    selected = decision.get("selected") or {}
    provider, model = current.get("provider"), current.get("model")
    from .supervision import thinking_of
    if ((current.get("labels") or {}).get("flow.role") in {"programmer","reviewer"}
            or selected.get("provider") != provider or selected.get("id") != model
            or selected.get("thinking_option_id") != thinking_of(current)):
        raise CapacityUnavailable("existing_manager_role_or_model_mismatch")
    cwd = str(core.manager_cwd(current.get("cwd")))
    agent = current["id"]
    request = "adopt-manager-" + str(chat_id) + "-" + agent
    ticket = sign_ticket({"v":1,"role":"manager","provider":provider,"model":model,
        "effort":selected["thinking_option_id"],"request_id":request,"cwd":cwd,
        "chat_id":str(chat_id),"agent_id":agent,"decision_fp":publish_decision(str(chat_id),"manager",decision)}, _token())
    db.execute("""INSERT OR REPLACE INTO admission_tickets(request_id,agent_id,chat_id,role,provider,model,effort,cwd,ticket_json,bound_at)
        VALUES(?,?,?,'manager',?,?,?,?,?,?)""", (request,agent,str(chat_id),provider,model,ticket["effort"],cwd,json.dumps(ticket),time.time()))
    _mirror_ticket(_admission_db(), agent, ticket)
    reserve_manager(db, str(chat_id), agent)


def resume_current_manager(db, route, current, key, catalog, limits):
    """Replay one durable same-owner continuation after fresh quota recovery."""
    from . import core, supervision
    message = str(current.get("lastError") or current.get("error") or "")
    if (current.get("status") in {"canceled", "cancelled", "stopped", "terminated"}
            or current.get("archivedAt") or current.get("cancelledAt") or current.get("canceledAt")
            or (message and not supervision.explicit_quota_text(message))):
        return
    row = db.execute("""SELECT * FROM manager_quota_resumes WHERE agent_id=?
        AND error_at IS NOT NULL ORDER BY error_at DESC LIMIT 1""", (current['id'],)).fetchone()
    if not row or row['completed']:
        return
    # An empty state classifies only this catalog, so retained positives cannot
    # authorize a resume when today's quota is unknown or stale.
    fresh = runtime().absorb_catalog(None, catalog, limits)['evidence'].get(current.get('provider'), {})
    if fresh.get('status') != 'available' or (fresh.get('observed_at') or 0) <= row['error_at']:
        return
    intent = json.loads(row['intent']) if row['intent'] else None
    if intent is None:
        intent = {'prompt': supervision.handoff(db, route, current['id'], key),
                  'message_id': str(uuid.uuid5(uuid.NAMESPACE_URL,
                      f"manager-quota-resume-{current['id']}-{row['signature']}"))}
        db.execute("UPDATE manager_quota_resumes SET intent=? WHERE agent_id=? AND signature=?",
                   (json.dumps(intent), current['id'], row['signature']))
        db.commit()
    try:
        core.bridge('send', agentId=current['id'], prompt=intent['prompt'],
                    options={'messageId': intent['message_id'], 'activeTurnBehavior': 'steer'})
    except Exception:
        return  # Lost ACK keeps the exact prompt, identity and owner for replay.
    db.execute("UPDATE manager_quota_resumes SET completed=1 WHERE agent_id=? AND signature=?",
               (current['id'], row['signature']))
    db.commit()


def reconcile_manager_route(db, route, agents, settings):
    """Policy-owned manager route. Returns True so the legacy switch does not also run."""
    import uuid
    from . import core, supervision
    if route.get("state") == "superseded" or (route.get("next_check") or 0) > time.time():
        return True
    from .operator_hold import active as held
    if held():return True
    primary = agents.get(route["primary_id"])
    if not primary or primary.get("archivedAt"):
        return True
    owners = (route["primary_id"], route["active_id"])
    expr = _chat_expr(db)
    jobs = db.execute(
        f"""SELECT jobs.id, {expr} AS chat_id, jobs.state, jobs.supervisor_id FROM jobs
            LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id
            WHERE jobs.supervisor_id IN (?,?)""", owners).fetchall()
    if jobs and all(job["state"] in {"paused", "canceled", "cancelled"} for job in jobs):
        return True
    current = agents.get(route["active_id"]) or primary
    if supervision.busy(current):
        return True
    if str(route.get("state") or "").startswith("switching_"):
        supervision.transition(db, route, primary, settings, agents)
        return True
    admission = db.execute("SELECT chat_id FROM admission_tickets WHERE agent_id=? AND role='manager'", (route["primary_id"],)).fetchone()
    chat_id = admission["chat_id"] if admission else route["primary_id"]
    for job in jobs:
        if job["state"] not in {"paused", "canceled", "cancelled"}:
            chat_id = job["chat_id"] or route["primary_id"]
            break
    catalog = {}
    catalog_path = core.STATE / "catalog.json"
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text())
    from .model_limits import load_limits
    limits = load_limits()
    local_state = load_state(db, str(chat_id), "manager")
    db.execute("""CREATE TABLE IF NOT EXISTS manager_quota_events(
        agent_id TEXT, signature TEXT, PRIMARY KEY(agent_id,signature))""")
    db.execute("""CREATE TABLE IF NOT EXISTS manager_quota_resumes(
        agent_id TEXT, signature TEXT, error_at REAL, intent TEXT, completed INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(agent_id,signature))""")
    event = supervision.quota_event(current, route.get("blocked_at") or 0)
    if event:
        message, event_at = event
        provider = current.get("provider")
        identity = message if event_at is None else json.dumps([message, event_at])
        signature = hashlib.sha256(identity.encode()).hexdigest()
        if not db.execute("SELECT 1 FROM manager_quota_events WHERE agent_id=? AND signature=?", (current['id'],signature)).fetchone():
            # Untimed legacy errors retain their old one-shot compatibility key.
            moment = event_at if event_at is not None else time.time()
            local_state = runtime().note_exhaustion(local_state, provider, moment, message)
            _publish_exhaustion(provider, moment,message)
            db.execute("INSERT INTO manager_quota_events VALUES(?,?)", (current['id'],signature))
            db.execute("INSERT OR IGNORE INTO manager_quota_resumes(agent_id,signature,error_at) VALUES(?,?,?)",
                       (current['id'], signature, event_at))
            save_state(db, str(chat_id), "manager", local_state, {"reason": "explicit_quota", "provider": provider})
            db.execute("UPDATE supervisor_routes SET blocked_at=? WHERE primary_id=?", (moment, route['primary_id']))
            db.commit()
    decision = select_for_role(
        catalog, {"specialty": "planning", "supervisor_role": True}, limits,
        state=absorb_global(local_state, catalog, limits))
    save_state(db, str(chat_id), "manager", decision.get("policy_state"), {"reason": decision.get("reason")})
    selected = decision.get("selected")
    if not selected:
        return True
    key = selected["provider"] + "/" + selected["id"]
    effort = selected["thinking_option_id"]
    current_key = str(current.get("provider") or "") + "/" + str(current.get("model") or "")
    current_effort = supervision.thinking_of(current) or settings.get("primary_thinking")
    adaptive_same = (key == 'codex/gpt-6.1-sol' and (settings.get('adaptive_effort') or {}).get('enabled')
                     and current_effort in {'medium','high'} and effort in {'medium','high'})
    if current_key == key and (current_effort == effort or adaptive_same):
        if adaptive_same:
            decision = {**decision, 'selected': {**selected, 'thinking_option_id': current_effort}}
        ensure_current_manager_ticket(db, str(chat_id), current, decision)
        single_manager(db, str(chat_id), route["active_id"])
        db.commit()
        resume_current_manager(db, route, current, key, catalog, limits)
        return True
    generation = int(route.get("generation") or 0) + 1
    request_key = f"supervisor-route-{route['primary_id']}-{generation}-{selected['provider']}-{selected['id']}-{effort}"
    if route.get("pending"):
        pending = json.loads(route["pending"]) if isinstance(route["pending"], str) else route["pending"]
        if isinstance(pending, dict) and pending.get("request_key") == request_key:
            return True
    primary_key = str(primary.get("provider") or "") + "/" + str(primary.get("model") or "")
    if (key == settings.get("primary_model") and effort == settings.get("primary_thinking")
            and primary_key == key and supervision.thinking_of(primary) == effort):
        prompt = supervision.handoff(db, route, route["active_id"], key)
        message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"supervisor-return-{route['primary_id']}-{generation}-{key}-{effort}"))
        ensure_current_manager_ticket(db, str(chat_id), primary, decision)
        pending = {"prompt": prompt, "message_id": message_id, "request_key": request_key}
        db.execute("""UPDATE supervisor_routes SET state='switching_to_primary', generation=?, pending=?, updated=?
            WHERE primary_id=?""", (generation, json.dumps(pending), time.time(), route["primary_id"]))
        db.commit()
        fresh = dict(db.execute("SELECT * FROM supervisor_routes WHERE primary_id=?", (route["primary_id"],)).fetchone())
        supervision.transition(db, fresh, primary, settings, agents)
        single_manager(db, str(chat_id), route["primary_id"])
        db.commit()
        return True
    prompt = supervision.handoff(db, route, route["active_id"], key)
    action, options = manager_launch_options(db, str(chat_id), primary.get("cwd"), prompt, request_key, decision)
    reserve_manager(db, str(chat_id), options["agentId"])
    pending = {
        "cwd": primary.get("cwd"), "workspace_id": primary.get("workspaceId"), "prompt": prompt,
        "request_key": request_key, "options": options, "action": action,
    }
    db.execute("""UPDATE supervisor_routes SET state='switching_to_fallback', generation=?, pending=?, updated=?
        WHERE primary_id=?""", (generation, core.encoded(pending), time.time(), route["primary_id"]))
    db.commit()
    fresh = dict(db.execute("SELECT * FROM supervisor_routes WHERE primary_id=?", (route["primary_id"],)).fetchone())
    supervision.transition(db, fresh, primary, settings, agents)
    return True


def native_prepare_manager(config, agent_id=None, env=None, purpose=None):
    """Return options for the SDK's existing create; never create/send an agent here.

    Preview without an ID only reads the coordinator. An actual create requires
    the local authenticated, subscription catalog as well as global quota state.
    """
    from . import core
    from .model_limits import load_limits
    role = (config.get("labels") or {}).get("flow.role") or (env or {}).get("PASEO_FLOW_ROLE") or config.get("role")
    if any(value in {"programmer", "reviewer"} for value in ((config.get("labels") or {}).get("flow.role"), (env or {}).get("PASEO_FLOW_ROLE"), config.get("role"))):
        raise CapacityUnavailable("worker_cannot_bootstrap_manager")
    if config.get("internal") or config.get("discovery") or config.get("metadataOnly") or purpose and purpose != "interactive":
        return config
    limits = load_limits()
    client, _ = open_client()
    client.status()  # authenticated coordinator, never a manual quota environment
    catalog_path = Path(os.environ.get("PASEO_CATALOG_FILE", core.STATE / "catalog.json"))
    catalog = json.loads(catalog_path.read_text()) if catalog_path.is_file() else {}
    viewed = client.observe(catalog, limits)
    state = viewed.get("state") or {}
    preview = runtime().evaluate("manager", {}, limits, state=state)
    if preview.get("wait") or not preview.get("model_key"):
        raise CapacityUnavailable("manager_wait:" + str(preview.get("reason")))
    choice = {"provider": preview["provider"], "model": preview["model"],
              "thinkingOptionId": preview["thinking_option"],
              "modeId": {"codex": "full-access", "claude": "bypassPermissions"}.get(preview["provider"])}
    if not agent_id:
        return {**config, **choice}
    catalog_path = Path(os.environ.get("PASEO_CATALOG_FILE", core.STATE / "catalog.json"))
    catalog = json.loads(catalog_path.read_text())
    db = sqlite3.connect(_flow_db(), timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN IMMEDIATE")
        migrate_flow(db)
        # A legacy idle original cannot reclaim a chat from its current owner.
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        prior_route = None
        if "supervisor_routes" in tables:
            prior_route = db.execute("""SELECT primary_id,active_id FROM supervisor_routes WHERE
                ? IN (primary_id,active_id,fallback_id) AND state!='superseded' ORDER BY updated DESC LIMIT 1""", (str(agent_id),)).fetchone()
            if prior_route and prior_route["active_id"] != agent_id:
                raise CapacityUnavailable("inactive_manager_owner")
        # UUID supplied by AgentManager remains the chat identity on retries.
        chat = prior_route["primary_id"] if prior_route else str(agent_id)
        decision = select_for_role(catalog, {"supervisor_role": True}, limits, state=state)
        if not decision.get("selected"):
            raise CapacityUnavailable("manager_wait:" + str(decision.get("reason")))
        options = {**config, **choice, "agentId": agent_id,
                   "idempotencyKey": "native-manager-" + str(agent_id), "env": dict(env or {}),
                   "labels": {**config.get("labels", {}), "flow.logical_primary": "etapa2-supervisor"}}
        _, options = prepare_native_launch(db, {"id": "native-manager-" + str(agent_id), "supervisor_role": True},
                                          {"id": chat, "chat_id": chat}, decision, options)
        reserve_manager(db, chat, agent_id)
        db.commit()
        return options
    finally:
        db.close()


def retry_quota_publications(db):
    db.execute("CREATE TABLE IF NOT EXISTS pending_quota_publications(provider TEXT PRIMARY KEY,at REAL NOT NULL,message TEXT)")
    for row in db.execute('SELECT provider,at,message FROM pending_quota_publications').fetchall():
        try:_publish_exhaustion(row['provider'],row['at'],row['message'] or 'quota exhausted')
        except Exception:continue
        db.execute('DELETE FROM pending_quota_publications WHERE provider=? AND at=?',(row['provider'],row['at']))
    db.commit()
