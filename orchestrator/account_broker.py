"""SQLite account coordinator. One Codex account, both hosts, loopback HTTP."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from .account_client import CapacityUnavailable
    from .policy_runtime import absorb_catalog, evaluate, OBSERVATION_KEYS
except ImportError:
    from account_client import CapacityUnavailable
    from policy_runtime import absorb_catalog, evaluate, OBSERVATION_KEYS

PROGRAMMER_CAP = 8
REVIEWER_CAP = 2
CHAT_WORKER_CAP = 10
DEFAULT_PENDING_TTL = 30.0
DEFAULT_BACKLOG_LIMIT = 8
DEFAULT_STARVATION = 4
ROLES = {"manager", "programmer", "reviewer"}
PROVIDERS = ("codex-programmer", "codex", "claude", "grok", "antigravity", "antigravity2", "antigravity3")
TERMINAL_KINDS = {"completed", "cancelled", "canceled"}


def tokens_equal(presented, expected):
    left = str(presented or "").encode("utf-8")
    right = str(expected or "").encode("utf-8")
    if len(left) != len(right):
        hmac.compare_digest(right, right)
        return False
    return hmac.compare_digest(left, right)


class Broker:
    def __init__(self, db_path, token, account_id="shared-codex"):
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("account_id")
        self.db_path = str(db_path)
        self.token = str(token or "")
        self.account_id = account_id.strip()
        self._ensure_schema()

    def observe(self, catalog, limits, *, host_id, account_id=None, now=None):
        self._check_account(account_id)
        host = _text(host_id, "host_id")
        if not isinstance(catalog, (dict, list)):
            raise ValueError("catalog")
        if limits is None:
            limits = {}
        if not isinstance(limits, dict):
            raise ValueError("limits")
        moment = _now(now)
        with self._immediate() as conn:
            state = _load_state(conn)
            absorbed = absorb_catalog(state, catalog, limits, now=moment)
            _save_policy(conn, absorbed["state"], limits, moment)
            conn.execute("INSERT OR REPLACE INTO host_policy_limits VALUES(?,?)", (host, json.dumps(limits)))
            _touch_host(conn, host, moment)
            counts = _counts(conn)
        return _view(self.account_id, host, absorbed, counts)

    def register(self, host_id, chat_id, candidates, *, replace=True, account_id=None, now=None):
        self._check_account(account_id)
        host = _text(host_id, "host_id")
        chat = _text(chat_id, "chat_id")
        if not isinstance(candidates, list):
            raise ValueError("candidates")
        moment = _now(now)
        with self._immediate() as conn:
            ttl = _pending_ttl(_load_limits(conn))
            _expire_pending(conn, moment, ttl)
            kept = []
            for candidate in candidates:
                kept.append(_upsert_ready(conn, host, chat, candidate, moment))
            if replace:
                _withdraw_missing(conn, host, chat, kept)
            _touch_host(conn, host, moment)
        return {"ok": True, "registered": len(kept)}

    def acquire(self, host_id, chat_id, task_id, role, request_id, metadata=None, *, account_id=None, now=None):
        self._check_account(account_id)
        host = _text(host_id, "host_id")
        chat = _text(chat_id, "chat_id")
        task = _text(task_id, "task_id")
        role_name = _role(role)
        request = _text(request_id, "request_id")
        meta = metadata or {}
        if not isinstance(meta, dict):
            raise ValueError("metadata")
        generation = _generation(meta.get("generation", 1))
        moment = _now(now)
        with self._immediate() as conn:
            host_limits = conn.execute("SELECT limits_json FROM host_policy_limits WHERE host_id=?", (host,)).fetchone()
            limits = json.loads(host_limits[0]) if host_limits else _load_limits(conn)
            ttl = _pending_ttl(limits)
            _expire_pending(conn, moment, ttl)
            for extra in meta.get("ready_candidates") or []:
                if isinstance(extra, dict):
                    _upsert_ready(conn, host, extra.get("chat_id") or chat, extra, moment)
            phase = meta.get("phase") or _default_phase(role_name)
            _upsert_ready(
                conn,
                host,
                chat,
                {
                    "task_id": task,
                    "role": role_name,
                    "request_id": request,
                    "generation": generation,
                    "phase": phase,
                },
                moment,
            )
            _touch_host(conn, host, moment)
            existing = _find_lease(conn, host, chat, task, role_name, generation)
            mode = _account_mode(conn)
            if existing is not None:
                if existing["state"] == "held":
                    return _grant_body(existing, granted=True, reason="idempotent_replay", mode=mode, wait=False)
                return _grant_body(existing, granted=False, reason="already_released", mode=mode, wait=False)
            if meta.get("adopt_existing") is True:
                return self._adopt(conn, host, chat, task, role_name, request, generation, phase, meta, moment, mode)
            state = _load_state(conn)
            if role_name == 'programmer' and (limits.get('programming') or {}).get('emergency_original_account', {}).get('enabled'):
                # Routing continuity belongs to this chat, never the last chat
                # that happened to acquire a lease on the shared account.
                previous = conn.execute("SELECT model_key FROM leases WHERE host_id=? AND chat_id=? AND role='programmer' ORDER BY granted_at DESC LIMIT 1", (host,chat)).fetchone()
                state.setdefault('decisions', {}).pop('programmer', None)
                if previous: state['decisions']['programmer'] = {'model_key':previous['model_key']}
            decision = evaluate(role_name, {"models": []}, limits, now=moment, state=state, implementation_model=meta.get("implementation_model"), review_task=meta.get("review_context"))
            _save_policy(conn, decision["state"], limits, moment)
            mode = "gpt_only" if decision["gpt_only"] else "normal"
            if _selection_differs(meta, decision):
                return _policy_changed(decision, mode)
            if decision["wait"] or not decision["model_key"]:
                return _denied("queued_by_policy", mode, wait=True)
            if role_name == "manager":
                return self._grant_manager(conn, host, chat, task, request, generation, phase, decision, moment, mode)
            preferred = _preferred_chat(conn, role_name, moment, ttl)
            if preferred != chat:
                return _denied("fair_queue", mode, wait=True)
            if (decision.get('evidence',{}).get(decision.get('provider'),{}) or {}).get('status')=='recovery_due':
                held=conn.execute("SELECT 1 FROM leases WHERE provider=? AND state='held' LIMIT 1",(decision['provider'],)).fetchone()
                if held:return _denied('quota_recovery_in_progress',mode,wait=True)
            if _chat_workers(conn, chat) >= CHAT_WORKER_CAP:
                return _denied("chat_cap", mode, wait=True)
            counts_as_gpt = 1 if decision["provider"] == "codex" else 0
            if mode == "gpt_only" and counts_as_gpt:
                cap = PROGRAMMER_CAP if role_name == "programmer" else REVIEWER_CAP
                held = _gpt_held(conn, role_name)
                if held >= cap:
                    reason = "account_programmer_cap" if role_name == "programmer" else "account_reviewer_cap"
                    return _denied(reason, mode, wait=True)
            if role_name == "programmer" and _review_blocks(conn, decision["state"], limits, moment, ttl):
                deferrals = _deferrals(conn, host, chat, task, role_name, generation) + 1
                limit = _starvation_limit(limits)
                if deferrals <= limit:
                    _set_deferrals(conn, host, chat, task, role_name, generation, deferrals)
                    return _denied("review_priority", mode, wait=True)
            return self._insert_lease(
                conn,
                host,
                chat,
                task,
                role_name,
                request,
                generation,
                phase,
                decision["model_key"],
                decision["provider"],
                decision["thinking_option"],
                counts_as_gpt,
                grandfather=0,
                moment=moment,
                mode=mode,
                reason="granted",
                agent_id=None,
            )

    def bind(self, lease_id, agent_id, *, host_id, account_id=None, now=None):
        self._check_account(account_id)
        host = _text(host_id, "host_id")
        lease = _text(lease_id, "lease_id")
        agent = _text(agent_id, "agent_id")
        moment = _now(now)
        with self._immediate() as conn:
            row = _lease_by_id(conn, lease)
            if row is None:
                return {"bound": False, "lease_id": lease, "agent_id": None, "reason": "unknown_lease"}
            if row["host_id"] != host:
                return {"bound": False, "lease_id": lease, "agent_id": row["bound_agent_id"], "reason": "host_mismatch"}
            if row["state"] != "held":
                return {"bound": False, "lease_id": lease, "agent_id": row["bound_agent_id"], "reason": "already_released"}
            if row["bound_agent_id"] and row["bound_agent_id"] != agent:
                return {"bound": False, "lease_id": lease, "agent_id": row["bound_agent_id"], "reason": "agent_mismatch"}
            conn.execute(
                "UPDATE leases SET bound_agent_id=?, bound_at=? WHERE lease_id=? AND state='held'",
                (agent, moment, lease),
            )
            _touch_host(conn, host, moment)
        return {"bound": True, "lease_id": lease, "agent_id": agent, "reason": "bound"}

    def release(self, lease_id, terminal_evidence, *, host_id, account_id=None, now=None):
        self._check_account(account_id)
        host = _text(host_id, "host_id")
        lease = _text(lease_id, "lease_id")
        moment = _now(now)
        with self._immediate() as conn:
            row = _lease_by_id(conn, lease)
            if row is None:
                return {"released": False, "lease_id": lease, "reason": "unknown_lease"}
            if row["host_id"] != host:
                return {"released": False, "lease_id": lease, "reason": "host_mismatch"}
            if row["state"] == "released":
                return {"released": True, "lease_id": lease, "reason": "already_released"}
            reason = _terminal_reason(row, terminal_evidence)
            if reason != "released":
                return {"released": False, "lease_id": lease, "reason": reason}
            conn.execute(
                """UPDATE leases SET state='released', released_at=?, terminal_evidence=?
                   WHERE lease_id=? AND state='held'""",
                (moment, json.dumps(terminal_evidence, sort_keys=True), lease),
            )
            conn.execute(
                """UPDATE candidates SET state='done' WHERE host_id=? AND chat_id=? AND task_id=?
                   AND role=? AND generation=?""",
                (row["host_id"], row["chat_id"], row["task_id"], row["role"], row["generation"]),
            )
            _touch_host(conn, host, moment)
        return {"released": True, "lease_id": lease, "reason": "released"}

    def heartbeat(self, host_id, chat_id=None, *, account_id=None, now=None):
        self._check_account(account_id)
        host = _text(host_id, "host_id")
        moment = _now(now)
        with self._immediate() as conn:
            if chat_id is None:
                cursor = conn.execute(
                    "UPDATE candidates SET heartbeat_at=? WHERE host_id=? AND state='ready'",
                    (moment, host),
                )
            else:
                chat = _text(chat_id, "chat_id")
                cursor = conn.execute(
                    "UPDATE candidates SET heartbeat_at=? WHERE host_id=? AND chat_id=? AND state='ready'",
                    (moment, host, chat),
                )
            _touch_host(conn, host, moment)
            renewed = cursor.rowcount
        return {"ok": True, "renewed": renewed}

    def reconcile(self, host_id, known_lease_ids, *, account_id=None, now=None):
        self._check_account(account_id)
        host = _text(host_id, "host_id")
        if not isinstance(known_lease_ids, list) or not all(isinstance(item, str) for item in known_lease_ids):
            raise ValueError("known_lease_ids")
        moment = _now(now)
        with self._immediate() as conn:
            _touch_host(conn, host, moment)
            rows = conn.execute(
                "SELECT lease_id FROM leases WHERE host_id=? AND state='held' ORDER BY lease_id",
                (host,),
            ).fetchall()
        retained = [row["lease_id"] for row in rows]
        return {"ok": True, "retained": retained, "released": [], "ignored_unknown": True}

    def status(self, *, host_id, account_id=None):
        self._check_account(account_id)
        host = _text(host_id, "host_id")
        with self._read() as conn:
            state = _load_state(conn)
            counts = _counts(conn)
            leases = [
                _public_lease(row)
                for row in conn.execute(
                    "SELECT * FROM leases WHERE state='held' ORDER BY granted_at, lease_id"
                )
            ]
        return {
            "ok": True,
            "account_id": self.account_id,
            "host_id": host,
            "gpt_only": state.get("account_mode") == "gpt_only",
            "account_mode": state.get("account_mode") or "normal",
            "evidence": _evidence_of(state),
            "counts": counts,
            "leases": leases,
        }

    def serve(self, host="127.0.0.1", port=6771):
        httpd = self._server(host, port)
        sys.stdout.write(json.dumps({"url": _public_url(httpd), "account_id": self.account_id}) + "\n")
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()

    def serve_in_thread(self, host="127.0.0.1", port=0):
        httpd = self._server(host, port)
        import threading

        thread = threading.Thread(target=httpd.serve_forever, name="account-broker", daemon=True)
        thread.start()
        httpd.ready_thread = thread
        return httpd

    def _server(self, host, port):
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("loopback bind required")
        address = ("127.0.0.1" if host == "localhost" else host, int(port))
        return CoordinatorServer(address, self, self.token)

    def _adopt(self, conn, host, chat, task, role_name, request, generation, phase, meta, moment, mode):
        if role_name == "manager":
            return _denied("adopt_requires_model", mode, wait=False)
        model_key = meta.get("model_key")
        if not isinstance(model_key, str) or "/" not in model_key:
            return _denied("adopt_requires_model", mode, wait=False)
        provider, _, _model = model_key.partition("/")
        if provider not in PROVIDERS:
            return _denied("adopt_requires_model", mode, wait=False)
        thinking = meta.get("thinking_option") or "medium"
        if not isinstance(thinking, str):
            raise ValueError("thinking_option")
        counts_as_gpt = 1 if provider == "codex" and role_name in {"programmer", "reviewer"} else 0
        agent = meta.get("agent_id")
        if agent is not None:
            agent = _text(agent, "agent_id")
        return self._insert_lease(
            conn,
            host,
            chat,
            task,
            role_name,
            request,
            generation,
            phase,
            model_key,
            provider,
            thinking,
            counts_as_gpt,
            grandfather=1,
            moment=moment,
            mode=mode,
            reason="adopted",
            agent_id=agent,
        )

    def _grant_manager(self, conn, host, chat, task, request, generation, phase, decision, moment, mode):
        current = conn.execute(
            "SELECT * FROM leases WHERE chat_id=? AND role='manager' AND state='held' ORDER BY granted_at LIMIT 1",
            (chat,),
        ).fetchone()
        if current is not None:
            return _grant_body(current, granted=False, reason="manager_active", mode=mode, wait=False)
        return self._insert_lease(
            conn,
            host,
            chat,
            task,
            "manager",
            request,
            generation,
            phase,
            decision["model_key"],
            decision["provider"],
            decision["thinking_option"],
            0,
            grandfather=0,
            moment=moment,
            mode=mode,
            reason="granted",
            agent_id=None,
        )

    def _insert_lease(
        self,
        conn,
        host,
        chat,
        task,
        role_name,
        request,
        generation,
        phase,
        model_key,
        provider,
        thinking,
        counts_as_gpt,
        grandfather,
        moment,
        mode,
        reason,
        agent_id,
    ):
        lease_id = "lease-" + uuid.uuid4().hex
        conn.execute(
            """INSERT INTO leases (
                   lease_id, account_id, host_id, chat_id, task_id, role, generation, request_id,
                   phase, model_key, provider, thinking_option, counts_as_gpt, grandfather, state,
                   granted_at, bound_agent_id, bound_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'held', ?, ?, ?)""",
            (
                lease_id,
                self.account_id,
                host,
                chat,
                task,
                role_name,
                generation,
                request,
                phase,
                model_key,
                provider,
                thinking,
                counts_as_gpt,
                grandfather,
                moment,
                agent_id,
                moment if agent_id else None,
            ),
        )
        conn.execute(
            """UPDATE candidates SET state='leased', deferrals=0 WHERE host_id=? AND chat_id=? AND task_id=?
               AND role=? AND generation=?""",
            (host, chat, task, role_name, generation),
        )
        conn.execute(
            """INSERT INTO chat_grants (chat_id, role, last_grant_at) VALUES (?,?,?)
               ON CONFLICT(chat_id, role) DO UPDATE SET last_grant_at=excluded.last_grant_at""",
            (chat, role_name, moment),
        )
        row = _lease_by_id(conn, lease_id)
        return _grant_body(row, granted=True, reason=reason, mode=mode, wait=False)

    def _check_account(self, account_id):
        if account_id is not None and account_id != self.account_id:
            raise CapacityUnavailable("account mismatch")

    def _ensure_schema(self):
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    account_id TEXT NOT NULL,
                    policy_state TEXT NOT NULL DEFAULT '{}',
                    limits_json TEXT NOT NULL DEFAULT '{}',
                    updated REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS host_policy_limits (host_id TEXT PRIMARY KEY, limits_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS hosts (
                    host_id TEXT PRIMARY KEY,
                    last_seen REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    host_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    request_id TEXT NOT NULL,
                    phase TEXT,
                    state TEXT NOT NULL,
                    registered_at REAL NOT NULL,
                    heartbeat_at REAL NOT NULL,
                    deferrals INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (host_id, chat_id, task_id, role, generation)
                );
                CREATE TABLE IF NOT EXISTS leases (
                    lease_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    host_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    request_id TEXT NOT NULL,
                    phase TEXT,
                    model_key TEXT,
                    provider TEXT,
                    thinking_option TEXT,
                    counts_as_gpt INTEGER NOT NULL DEFAULT 0,
                    grandfather INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL,
                    granted_at REAL NOT NULL,
                    bound_agent_id TEXT,
                    bound_at REAL,
                    released_at REAL,
                    terminal_evidence TEXT,
                    UNIQUE (host_id, chat_id, task_id, role, generation)
                );
                CREATE TABLE IF NOT EXISTS chat_grants (
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    last_grant_at REAL NOT NULL,
                    PRIMARY KEY (chat_id, role)
                );
                """
            )
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT account_id FROM meta WHERE id=1").fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO meta (id, account_id, policy_state, limits_json, updated) VALUES (1, ?, '{}', '{}', 0)",
                        (self.account_id,),
                    )
                elif row["account_id"] != self.account_id:
                    raise CapacityUnavailable("account mismatch")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    @contextmanager
    def _immediate(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            conn.close()
            raise
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        finally:
            conn.close()

    @contextmanager
    def _read(self):
        conn = self._connect()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


class CoordinatorServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, broker, token):
        self.broker = broker
        self.token = token
        super().__init__(address, CoordinatorHandler)


class CoordinatorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        path = self.path.split("?", 1)[0]
        sys.stderr.write("%s %s\n" % (self.command, path))

    def do_GET(self):
        if self.path.split("?", 1)[0] != "/v1/status":
            return self._send(404, {"ok": False, "reason": "not_found"})
        if not self._authorized():
            return self._send(401, {"ok": False, "reason": "unauthorized"})
        try:
            query = _query(self.path)
            body = self.server.broker.status(host_id=query.get("host_id"), account_id=query.get("account_id"))
        except CapacityUnavailable:
            return self._send(403, {"ok": False, "reason": "rejected"})
        except ValueError:
            return self._send(400, {"ok": False, "reason": "invalid"})
        except Exception:
            return self._send(500, {"ok": False, "reason": "unavailable"})
        return self._send(200, body)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        routes = {
            "/v1/observe": self._observe,
            "/v1/register": self._register,
            "/v1/acquire": self._acquire,
            "/v1/bind": self._bind,
            "/v1/release": self._release,
            "/v1/heartbeat": self._heartbeat,
            "/v1/reconcile": self._reconcile,
        }
        if path not in routes:
            return self._send(404, {"ok": False, "reason": "not_found"})
        if not self._authorized():
            return self._send(401, {"ok": False, "reason": "unauthorized"})
        try:
            payload = self._json()
            body = routes[path](payload)
        except CapacityUnavailable:
            return self._send(403, {"ok": False, "reason": "rejected"})
        except ValueError:
            return self._send(400, {"ok": False, "reason": "invalid"})
        except json.JSONDecodeError:
            return self._send(400, {"ok": False, "reason": "invalid"})
        except Exception:
            return self._send(500, {"ok": False, "reason": "unavailable"})
        return self._send(200, body)

    def _observe(self, payload):
        return self.server.broker.observe(
            payload.get("catalog"),
            payload.get("limits"),
            host_id=payload.get("host_id"),
            account_id=payload.get("account_id"),
            now=payload.get("now"),
        )

    def _register(self, payload):
        return self.server.broker.register(
            payload.get("host_id"),
            payload.get("chat_id"),
            payload.get("candidates"),
            replace=payload.get("replace", True),
            account_id=payload.get("account_id"),
            now=payload.get("now"),
        )

    def _acquire(self, payload):
        return self.server.broker.acquire(
            payload.get("host_id"),
            payload.get("chat_id"),
            payload.get("task_id"),
            payload.get("role"),
            payload.get("request_id"),
            payload.get("metadata") or {},
            account_id=payload.get("account_id"),
            now=payload.get("now"),
        )

    def _bind(self, payload):
        return self.server.broker.bind(
            payload.get("lease_id"),
            payload.get("agent_id"),
            host_id=payload.get("host_id"),
            account_id=payload.get("account_id"),
            now=payload.get("now"),
        )

    def _release(self, payload):
        return self.server.broker.release(
            payload.get("lease_id"),
            payload.get("terminal_evidence"),
            host_id=payload.get("host_id"),
            account_id=payload.get("account_id"),
            now=payload.get("now"),
        )

    def _heartbeat(self, payload):
        return self.server.broker.heartbeat(
            payload.get("host_id"),
            payload.get("chat_id"),
            account_id=payload.get("account_id"),
            now=payload.get("now"),
        )

    def _reconcile(self, payload):
        return self.server.broker.reconcile(
            payload.get("host_id"),
            payload.get("known_lease_ids"),
            account_id=payload.get("account_id"),
            now=payload.get("now"),
        )

    def _authorized(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return tokens_equal(header[7:].strip(), self.server.token)

    def _json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > 1_000_000:
            raise ValueError("size")
        raw = self.rfile.read(length) if length else b""
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("body")
        return parsed

    def _send(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def initialize(db_path, token_file, account_id="shared-codex"):
    path = Path(token_file)
    created = False
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_urlsafe(32)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, (secret + "\n").encode("utf-8"))
        finally:
            os.close(descriptor)
        created = True
    else:
        os.chmod(path, 0o600)
        secret = path.read_text(encoding="utf-8").strip()
    mode = os.stat(path).st_mode & 0o777
    if mode & 0o077:
        raise RuntimeError("token file must be mode 0600")
    if not secret:
        raise RuntimeError("token file empty")
    Broker(db_path, secret, account_id)
    return {"db": str(db_path), "token_file": str(path), "account_id": account_id, "created_token": created}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="account_broker")
    parser.add_argument("command", choices=("init", "serve", "status"))
    parser.add_argument("--db", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6771)
    parser.add_argument("--account-id", default="shared-codex")
    args = parser.parse_args(argv)
    if args.command == "init":
        result = initialize(args.db, args.token_file, args.account_id)
        sys.stdout.write(json.dumps(result) + "\n")
        return 0
    secret = _read_token(args.token_file)
    broker = Broker(args.db, secret, args.account_id)
    if args.command == "status":
        sys.stdout.write(json.dumps(broker.status(host_id="cli", account_id=args.account_id)) + "\n")
        return 0
    broker.serve(args.bind, args.port)
    return 0


def _read_token(path):
    file_path = Path(path)
    mode = os.stat(file_path).st_mode & 0o777
    if mode & 0o077:
        os.chmod(file_path, 0o600)
        mode = os.stat(file_path).st_mode & 0o777
    if mode & 0o077:
        raise RuntimeError("token file must be mode 0600")
    secret = file_path.read_text(encoding="utf-8").strip()
    if not secret:
        raise RuntimeError("token file empty")
    return secret


def _view(account_id, host, absorbed, counts):
    return {
        "ok": True,
        "account_id": account_id,
        "host_id": host,
        "gpt_only": absorbed["gpt_only"],
        "account_mode": absorbed["account_mode"],
        "evidence": absorbed["evidence"],
        "state": absorbed["state"],
        "counts": counts,
    }


def _public_url(httpd):
    host, port = httpd.server_address[:2]
    shown = "127.0.0.1" if host in {"127.0.0.1", "::1", "localhost"} else host
    return "http://%s:%s" % (shown, port)


def _query(path):
    from urllib.parse import parse_qs, urlsplit

    raw = parse_qs(urlsplit(path).query)
    return {key: values[-1] for key, values in raw.items() if values}


def _load_state(conn):
    row = conn.execute("SELECT policy_state FROM meta WHERE id=1").fetchone()
    if row is None or not row["policy_state"]:
        return {}
    try:
        parsed = json.loads(row["policy_state"])
    except json.JSONDecodeError as exc:
        raise CapacityUnavailable("coordinator state corrupt") from exc
    if not isinstance(parsed, dict):
        raise CapacityUnavailable("coordinator state corrupt")
    return parsed


def _load_limits(conn):
    row = conn.execute("SELECT limits_json FROM meta WHERE id=1").fetchone()
    if row is None or not row["limits_json"]:
        return {}
    try:
        parsed = json.loads(row["limits_json"])
    except json.JSONDecodeError as exc:
        raise CapacityUnavailable("coordinator state corrupt") from exc
    if not isinstance(parsed, dict):
        raise CapacityUnavailable("coordinator state corrupt")
    return parsed


def _save_policy(conn, state, limits, moment):
    conn.execute(
        "UPDATE meta SET policy_state=?, limits_json=?, updated=? WHERE id=1",
        (json.dumps(state, sort_keys=True), json.dumps(limits, sort_keys=True), moment),
    )


def _account_mode(conn):
    state = _load_state(conn)
    return "gpt_only" if state.get("account_mode") == "gpt_only" else "normal"


def _touch_host(conn, host, moment):
    conn.execute(
        "INSERT INTO hosts (host_id, last_seen) VALUES (?, ?) ON CONFLICT(host_id) DO UPDATE SET last_seen=excluded.last_seen",
        (host, moment),
    )


def _expire_pending(conn, moment, ttl):
    conn.execute(
        "UPDATE candidates SET state='withdrawn' WHERE state='ready' AND heartbeat_at < ?",
        (moment - ttl,),
    )


def _upsert_ready(conn, host, chat, candidate, moment):
    if not isinstance(candidate, dict):
        raise ValueError("candidate")
    task = _text(candidate.get("task_id"), "task_id")
    role_name = _role(candidate.get("role"))
    request = _text(candidate.get("request_id"), "request_id")
    generation = _generation(candidate.get("generation", 1))
    phase = candidate.get("phase") or _default_phase(role_name)
    if not isinstance(phase, str):
        raise ValueError("phase")
    own_chat = _text(candidate.get("chat_id") or chat, "chat_id")
    conn.execute(
        """INSERT INTO candidates (
               host_id, chat_id, task_id, role, generation, request_id, phase, state, registered_at, heartbeat_at, deferrals
           ) VALUES (?,?,?,?,?,?,?,'ready',?,?,0)
           ON CONFLICT(host_id, chat_id, task_id, role, generation) DO UPDATE SET
               request_id=excluded.request_id,
               phase=excluded.phase,
               state=CASE WHEN candidates.state='leased' THEN 'leased' ELSE 'ready' END,
               heartbeat_at=CASE WHEN candidates.state='leased' THEN candidates.heartbeat_at ELSE excluded.heartbeat_at END,
               deferrals=CASE WHEN candidates.state='ready' THEN candidates.deferrals ELSE 0 END
        """,
        (host, own_chat, task, role_name, generation, request, phase, moment, moment),
    )
    return (own_chat, task, role_name, generation)


def _withdraw_missing(conn, host, chat, kept):
    rows = conn.execute(
        "SELECT task_id, role, generation FROM candidates WHERE host_id=? AND chat_id=? AND state='ready'",
        (host, chat),
    ).fetchall()
    live = {(item[1], item[2], item[3]) for item in kept if item[0] == chat}
    for row in rows:
        if (row["task_id"], row["role"], row["generation"]) not in live:
            conn.execute(
                """UPDATE candidates SET state='withdrawn' WHERE host_id=? AND chat_id=? AND task_id=?
                   AND role=? AND generation=? AND state='ready'""",
                (host, chat, row["task_id"], row["role"], row["generation"]),
            )


def _find_lease(conn, host, chat, task, role_name, generation):
    return conn.execute(
        """SELECT * FROM leases WHERE host_id=? AND chat_id=? AND task_id=? AND role=? AND generation=?""",
        (host, chat, task, role_name, generation),
    ).fetchone()


def _lease_by_id(conn, lease_id):
    return conn.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()


def _preferred_chat(conn, role_name, moment, ttl):
    rows = conn.execute(
        """SELECT DISTINCT chat_id FROM candidates
           WHERE role=? AND state='ready' AND heartbeat_at >= ?""",
        (role_name, moment - ttl),
    ).fetchall()
    if not rows:
        return None

    def sort_key(chat_id):
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM leases WHERE chat_id=? AND role=? AND state='held'",
            (chat_id, role_name),
        ).fetchone()["n"]
        grant = conn.execute(
            "SELECT last_grant_at FROM chat_grants WHERE chat_id=? AND role=?",
            (chat_id, role_name),
        ).fetchone()
        last = float(grant["last_grant_at"]) if grant else 0.0
        return (active, last, chat_id)

    return min((row["chat_id"] for row in rows), key=sort_key)


def _chat_workers(conn, chat):
    return conn.execute(
        """SELECT COUNT(*) AS n FROM leases
           WHERE chat_id=? AND state='held' AND role IN ('programmer', 'reviewer')""",
        (chat,),
    ).fetchone()["n"]


def _gpt_held(conn, role_name):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM leases WHERE role=? AND state='held' AND counts_as_gpt=1",
        (role_name,),
    ).fetchone()["n"]


def _review_blocks(conn, state, limits, moment, ttl):
    policy = limits.get("runtime_policy") if isinstance(limits.get("runtime_policy"), dict) else {}
    try:
        backlog_limit = int(policy.get("review_backlog_limit", DEFAULT_BACKLOG_LIMIT))
    except (TypeError, ValueError):
        backlog_limit = DEFAULT_BACKLOG_LIMIT
    backlog_limit = max(0, backlog_limit)
    ready = conn.execute(
        """SELECT chat_id FROM candidates WHERE role='reviewer' AND state='ready' AND heartbeat_at >= ?""",
        (moment - ttl,),
    ).fetchall()
    if not ready:
        return False
    above_max = len(ready) > backlog_limit
    decision = evaluate("reviewer", {"models": []}, limits, now=moment, state=state)
    if decision["wait"]:
        return False
    if state.get("account_mode") == "gpt_only":
        if decision["provider"] != "codex":
            return False
        if _gpt_held(conn, "reviewer") < REVIEWER_CAP:
            return True
        return above_max
    for row in ready:
        if _chat_workers(conn, row["chat_id"]) < CHAT_WORKER_CAP:
            return True
    return above_max


def _deferrals(conn, host, chat, task, role_name, generation):
    row = conn.execute(
        """SELECT deferrals FROM candidates WHERE host_id=? AND chat_id=? AND task_id=? AND role=? AND generation=?""",
        (host, chat, task, role_name, generation),
    ).fetchone()
    return int(row["deferrals"]) if row else 0


def _set_deferrals(conn, host, chat, task, role_name, generation, value):
    conn.execute(
        """UPDATE candidates SET deferrals=? WHERE host_id=? AND chat_id=? AND task_id=? AND role=? AND generation=?""",
        (value, host, chat, task, role_name, generation),
    )


def _counts(conn):
    def number(sql, params=()):
        return conn.execute(sql, params).fetchone()["n"]

    by_chat = {}
    rows = conn.execute(
        """SELECT chat_id, role, COUNT(*) AS n FROM leases WHERE state='held' GROUP BY chat_id, role"""
    ).fetchall()
    for row in rows:
        slot = by_chat.setdefault(row["chat_id"], {"programmer": 0, "reviewer": 0, "manager": 0})
        slot[row["role"]] = row["n"]
    return {
        "programmers_gpt": number(
            "SELECT COUNT(*) AS n FROM leases WHERE state='held' AND role='programmer' AND counts_as_gpt=1"
        ),
        "reviewers_gpt": number(
            "SELECT COUNT(*) AS n FROM leases WHERE state='held' AND role='reviewer' AND counts_as_gpt=1"
        ),
        "programmers_held": number("SELECT COUNT(*) AS n FROM leases WHERE state='held' AND role='programmer'"),
        "reviewers_held": number("SELECT COUNT(*) AS n FROM leases WHERE state='held' AND role='reviewer'"),
        "by_chat": by_chat,
    }


def _evidence_of(state):
    observations = state.get("observations") if isinstance(state.get("observations"), dict) else {}
    evidence = {}
    for name in OBSERVATION_KEYS:
        current = observations.get(name)
        if isinstance(current, dict) and current.get("status") in {"available", "exhausted"}:
            evidence[name] = {"status": current["status"], "observed_at": current.get("observed_at")}
        else:
            evidence[name] = {"status": "unknown", "observed_at": None}
    return evidence


def _public_lease(row):
    return {
        "lease_id": row["lease_id"],
        "host_id": row["host_id"],
        "chat_id": row["chat_id"],
        "task_id": row["task_id"],
        "role": row["role"],
        "generation": row["generation"],
        "model_key": row["model_key"],
        "provider": row["provider"],
        "thinking_option": row["thinking_option"],
        "counts_as_gpt": bool(row["counts_as_gpt"]),
        "grandfather": bool(row["grandfather"]),
        "state": row["state"],
        "bound_agent_id": row["bound_agent_id"],
        "granted_at": row["granted_at"],
    }


def _grant_body(row, *, granted, reason, mode, wait):
    return {
        "granted": granted,
        "lease_id": None if row is None else row["lease_id"],
        "reason": reason,
        "mode": mode,
        "wait": wait,
        "model_key": None if row is None else row["model_key"],
        "provider": None if row is None else row["provider"],
        "model": None if row is None or not row["model_key"] else row["model_key"].split("/", 1)[-1],
        "thinking_option": None if row is None else row["thinking_option"],
        "grandfather": False if row is None else bool(row["grandfather"]),
    }


def _denied(reason, mode, wait):
    return _grant_body(None, granted=False, reason=reason, mode=mode, wait=wait)


def _selection_differs(meta, decision):
    if "requested_model_key" in meta and meta.get("requested_model_key") is not None:
        if meta.get("requested_model_key") != decision.get("model_key"):
            return True
    if "requested_thinking_option" in meta and meta.get("requested_thinking_option") is not None:
        if meta.get("requested_thinking_option") != decision.get("thinking_option"):
            return True
    return False


def _policy_changed(decision, mode):
    model_key = decision.get("model_key")
    model = decision.get("model")
    if model is None and isinstance(model_key, str) and "/" in model_key:
        model = model_key.split("/", 1)[1]
    return {
        "granted": False,
        "lease_id": None,
        "reason": "policy_changed",
        "mode": mode,
        "wait": bool(decision.get("wait")),
        "model_key": model_key,
        "provider": decision.get("provider"),
        "model": model,
        "thinking_option": decision.get("thinking_option"),
        "grandfather": False,
        "evidence": decision.get("evidence") or {},
    }


def _terminal_reason(row, evidence):
    if not isinstance(evidence, dict):
        return "evidence_not_terminal"
    kind = str(evidence.get("kind") or "").strip().lower()
    if kind not in TERMINAL_KINDS or evidence.get("confirmed") is False:
        return "evidence_not_terminal"
    if not row["bound_agent_id"]:
        return "not_bound"
    if evidence.get("agent_id") != row["bound_agent_id"]:
        return "agent_mismatch"
    return "released"


def _pending_ttl(limits):
    policy = limits.get("runtime_policy") if isinstance(limits.get("runtime_policy"), dict) else {}
    value = policy.get("pending_ttl_seconds", DEFAULT_PENDING_TTL)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DEFAULT_PENDING_TTL
    if number < 0:
        return DEFAULT_PENDING_TTL
    return number


def _starvation_limit(limits):
    policy = limits.get("runtime_policy") if isinstance(limits.get("runtime_policy"), dict) else {}
    try:
        number = int(policy.get("review_starvation_deferrals", DEFAULT_STARVATION))
    except (TypeError, ValueError):
        return DEFAULT_STARVATION
    return max(0, number)


def _default_phase(role_name):
    if role_name == "reviewer":
        return "review"
    if role_name == "manager":
        return "manage"
    return "implement"


def _role(value):
    if not isinstance(value, str) or value.strip().lower() not in ROLES:
        raise ValueError("role")
    return value.strip().lower()


def _generation(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("generation")
    return value


def _text(value, field, limit=200):
    if not isinstance(value, str):
        raise ValueError(field)
    text = value.strip()
    if not text or len(text) > limit:
        raise ValueError(field)
    return text


def _now(value):
    if value is None:
        return time.time()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("now")
    return float(value)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
