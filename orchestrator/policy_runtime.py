"""Role selection from the approved quota policy. Python stdlib only.

Observations are monotonic per provider. A later caller cannot re-apply an
older exhausted snapshot, and the clock alone never flips an accepted fact.
"""

from __future__ import annotations

import copy
import datetime
import re

PROVIDERS = ("codex-programmer", "codex", "claude", "grok", "antigravity", "antigravity2", "antigravity3")
ANTIGRAVITY_SONNET_KEY = "antigravity2/claude-sonnet-5-5-medium"
OBSERVATION_KEYS = PROVIDERS + (ANTIGRAVITY_SONNET_KEY,)
DEFAULT_MAX_AGE = 300.0
DEFAULT_MIN_REMAINING = 0.01

SOL_HIGH = ("codex/gpt-6.1-sol", "high")
SOL_MEDIUM = ("codex/gpt-6.1-sol", "medium")
TERRA_MEDIUM = ("codex-programmer/gpt-6.1-terra", "medium")
EMERGENCY_TERRA = ("codex/gpt-6.1-terra", "medium")
SONNET_HIGH = ("claude/claude-sonnet-5-5", "high")
GROK_MEDIUM = ("grok/grok-4.7", "medium")
GROK_HIGH = ("grok/grok-4.7", "high")
GEMINI_HIGH = ("antigravity/gemini-3.8-flash-high", "high")
GEMINI2_HIGH = ("antigravity2/gemini-3.8-flash-high", "high")
GEMINI_NEW2_HIGH = ("antigravity3/gemini-3.8-flash-high", "high")
ASTRA_MEDIUM = ("codex/gpt-6-astra", "medium")

_TRANSPORT_OR_AUTH = re.compile(
    r"auth|unauthor|forbidden|transport|connection|timed out|timeout|econn|network|\btls\b|\bssl\b|proxy",
    re.I,
)
_SLOT_ONLY = re.compile(r"\bslot\b|concurrency|too many requests|at capacity|\brate[ _-]?limit", re.I)
_QUOTA_TEXT = re.compile(
    r"quota[ _-]?(?:exceeded|exhausted|reached)|(?:usage|token|session)[ _-]?limit|hit your (?:session )?limit|out of (?:tokens|usage)|\busage balance exhausted\b",
    re.I,
)
_NON_QUOTA_STATUS = {
    "unknown",
    "auth",
    "auth_error",
    "unauthenticated",
    "unauthorized",
    "forbidden",
    "transport",
    "timeout",
    "timed_out",
    "rate",
    "rate_limited",
    "rate_limit",
    "concurrency",
    "saturated",
    "error",
    "generic_error",
    "unavailable",
}
_GENERIC_ERROR_STATUS = {"unknown", "error", "generic_error", "unavailable"}


def explicit_quota_text(message) -> bool:
    """True only for an unambiguous quota or session limit."""
    text = str(message or "")
    if not text or _TRANSPORT_OR_AUTH.search(text) or _SLOT_ONLY.search(text):
        return False
    return bool(_QUOTA_TEXT.search(text))


def note_exhaustion(state, provider, timestamp, reason) -> dict:
    """Record explicit provider exhaustion unless it is older than a known fact."""
    base = _blank_state(state)
    _ensure_observations(base)
    prov = _provider_name(provider)
    when = _timestamp(timestamp)
    if prov is None or when is None or not explicit_quota_text(reason):
        return base
    _accept(base, prov, "exhausted", when, str(reason))
    return base


def enabled_sonnet(limits):
    cfg=limits.get("antigravity_sonnet") or {}
    return bool(cfg.get("enabled") and "antigravity2" in enabled_gemini(limits))


def quota_key(value):
    """Gemini keeps its historical account key; partner model has separate evidence."""
    return ANTIGRAVITY_SONNET_KEY if value == ANTIGRAVITY_SONNET_KEY else str(value or "").split("/",1)[0]


def enabled_gemini(limits):
    cfg=limits.get('gemini') or {}
    if not cfg.get('enabled'):return set()
    explicit=cfg.get('enabled_provider_ids')
    if isinstance(explicit,list):return set(explicit)&{'antigravity','antigravity2','antigravity3'}
    return ({'antigravity'} if cfg.get('account1_enabled',True) else set()) | ({'antigravity2'} if cfg.get('account2_enabled') else set()) | ({'antigravity3'} if cfg.get('account3_enabled') else set())


def absorb_catalog(state, catalog, limits, *, now=None) -> dict:
    """Merge one catalog into the monotonic account state. Does not pick a role."""
    moment = _moment(now)
    max_age, minimum = _settings(limits)
    working = _blank_state(state)
    _ensure_observations(working)
    raw = _classify_catalog(catalog, moment, max_age, minimum)
    for name in OBSERVATION_KEYS:
        seen = raw[name]
        if seen["status"] in {"available", "exhausted"}:
            _accept(working, name, seen["status"], seen["observed_at"], seen["reason"])
    effective = _effective(working)
    for provider,record in effective.items():
        if record['status']=='available' and not _is_fresh(record['observed_at'],moment,max_age):
            effective[provider]={**record,'status':'unknown'}
    gpt_only = _mode(working, effective)
    if any(effective[name]["status"] != "exhausted" for name in enabled_gemini(limits)) or (enabled_sonnet(limits) and effective[ANTIGRAVITY_SONNET_KEY]["status"] != "exhausted") or ((limits.get("programmer_account") or {}).get("enabled") and effective["codex-programmer"]["status"] != "exhausted"):
        gpt_only = False
    working["account_mode"] = "gpt_only" if gpt_only else "normal"
    return {
        "state": working,
        "evidence": {
            name: {"status": effective[name]["status"], "observed_at": effective[name]["observed_at"]}
            for name in OBSERVATION_KEYS
        },
        "gpt_only": gpt_only,
        "account_mode": working["account_mode"],
    }


def evaluate(role, catalog, limits, *, now=None, state=None, implementation_model=None, review_task=None) -> dict:
    """Choose the approved model for one role from the monotonic account state."""
    moment = _moment(now)
    absorbed = absorb_catalog(state, catalog, limits, now=moment)
    working = absorbed["state"]
    effective = {
        name: absorbed["evidence"][name] for name in OBSERVATION_KEYS
    }
    gpt_only = absorbed["gpt_only"]
    normalized = str(role or '').strip().lower()
    # Only programming may attempt recovery; manager return still needs positive evidence.
    for provider in ((enabled_gemini(limits) | ({ANTIGRAVITY_SONNET_KEY} if enabled_sonnet(limits) else set())) if normalized=='programmer' else set()):
        record=working.get('observations',{}).get(provider) or {}
        if effective[provider]['status']=='exhausted' and moment>=recovery_after(record,limits):
            effective[provider]={**effective[provider],'status':'recovery_due'}
    normalized = str(role or "").strip().lower()
    previous = working["decisions"].get(normalized)
    previous_key = previous.get("model_key") if isinstance(previous, dict) else None
    choice = _select(normalized, effective, previous_key, bool((limits.get("gemini") or {}).get("enabled")), "antigravity2" in enabled_gemini(limits), "antigravity3" in enabled_gemini(limits), "antigravity" in enabled_gemini(limits), bool((limits.get("programmer_account") or {}).get("enabled")), bool((limits.get("programming") or {}).get("emergency_original_account", {}).get("enabled")), enabled_sonnet(limits), (limits.get("programmer_account") or {}).get("thinking", "medium"), (limits.get("programmer_account") or {}).get("model", "gpt-6.1-terra"), ((limits.get("programming") or {}).get("emergency_original_account") or {}).get("thinking_option", "medium"))
    if normalized == "manager" and choice["model_key"] == SOL_HIGH[0] and (limits.get("supervision") or {}).get("primary_thinking") == "medium":
        choice = _chosen(SOL_MEDIUM, "manager_primary_sol_medium")
    if normalized == "reviewer" and implementation_model == ANTIGRAVITY_SONNET_KEY and choice["model_key"] == SONNET_HIGH[0] and effective["codex"]["status"] != "exhausted":
        choice = _chosen(SOL_MEDIUM, "reviewer_independent_sol_for_antigravity_sonnet")
    risk = None
    adaptive_review=(limits.get('review') or {}).get('adaptive_effort') or {}
    if normalized == 'reviewer' and choice['model_key'] == SOL_MEDIUM[0] and adaptive_review.get('enabled'):
        from .task_risk import assess
        risk=assess(review_task)
        if risk['level']=='high':choice=_chosen(SOL_HIGH,'reviewer_sol_high_by_task_risk')
    external = isinstance(implementation_model, str) and implementation_model.split("/", 1)[0] in {"codex-programmer", "grok", "antigravity", "antigravity2", "antigravity3"}
    if normalized == "reviewer" and choice["model_key"] == SOL_MEDIUM[0] and choice["thinking_option"] == "medium" and external and (limits.get("review") or {}).get("sol_high_for_external_programmer"):
        choice = _chosen(SOL_HIGH, "reviewer_fallback_sol_high_external_programmer")
    decision = {
        "model_key": choice["model_key"],
        "provider": choice["provider"],
        "model": choice["model"],
        "thinking_option": choice["thinking_option"],
        "reason": choice["reason"],
        "at": moment,
        "wait": choice["wait"],
        "gpt_only": gpt_only,
    }
    if choice["reason"] != "invalid_role":
        working["decisions"][normalized] = decision
    return {
        "model_key": choice["model_key"],
        "provider": choice["provider"],
        "model": choice["model"],
        "thinking_option": choice["thinking_option"],
        "wait": choice["wait"],
        "reason": choice["reason"],
        "gpt_only": gpt_only,
        "state": working,
        "review_risk": risk,
        "evidence": effective,
    }


def recovery_after(record,limits):
    text=str(record.get("reason") or "")
    match=re.search(r"resets? in\s+((?:[0-9]+(?:\.[0-9]+)?\s*[dhms]\s*)+)",text,re.I)
    seconds=sum(float(n)*{"d":86400,"h":3600,"m":60,"s":1}[u.lower()] for n,u in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*([dhms])",match.group(1),re.I)) if match else float((limits.get("gemini") or {}).get("recovery_retry_seconds",3600))
    return float(record.get("observed_at") or 0)+max(60,seconds)


def _mode(working, effective):
    claude_exhausted = effective["claude"]["status"] == "exhausted"
    grok_exhausted = effective["grok"]["status"] == "exhausted"
    codex_status = effective["codex"]["status"]
    return (claude_exhausted and grok_exhausted and codex_status == "available") or (
        working.get("account_mode") == "gpt_only"
        and claude_exhausted
        and grok_exhausted
        and codex_status != "exhausted"
    )


def _select(role, effective, previous_key, gemini_enabled=False, gemini2_enabled=False, gemini3_enabled=False, gemini1_enabled=True, programmer_account=False, emergency_original=False, sonnet_enabled=False, dedicated_effort="medium", dedicated_model="gpt-6.1-terra", emergency_effort="medium"):
    codex = effective["codex"]["status"]
    claude = effective["claude"]["status"]
    grok = effective["grok"]["status"]
    if role == "manager":
        gemini_exhausted = (not gemini_enabled or not gemini1_enabled or effective["antigravity"]["status"] == "exhausted") and (not gemini2_enabled or effective["antigravity2"]["status"] == "exhausted") and (not gemini3_enabled or effective["antigravity3"]["status"] == "exhausted")
        other_programmers_exhausted = gemini_exhausted and (not sonnet_enabled or effective[ANTIGRAVITY_SONNET_KEY]["status"] == "exhausted") and (not programmer_account or effective["codex-programmer"]["status"] == "exhausted")
        if codex == "available" and claude == "exhausted" and grok == "exhausted" and other_programmers_exhausted:
            return _chosen(ASTRA_MEDIUM, "manager_astra_medium")
        if (
            previous_key == ASTRA_MEDIUM[0]
            and other_programmers_exhausted
            and claude == "exhausted"
            and grok == "exhausted"
            and codex != "exhausted"
        ):
            return _chosen(ASTRA_MEDIUM, "manager_astra_medium")
        if codex != "exhausted":
            return _chosen(SOL_HIGH, "manager_primary_sol_high")
        if claude == "available" or (previous_key == SONNET_HIGH[0] and claude != "exhausted"):
            return _chosen(SONNET_HIGH, "manager_fallback_sonnet_high")
        return _queued("manager_queued")
    if role == "programmer":
        if dedicated_effort not in {"medium", "high"}:return _queued("programmer_effort_forbidden")
        if dedicated_model not in {"gpt-6.1-terra", "gpt-6.1-sol"} or (dedicated_model=="gpt-6.1-sol" and dedicated_effort!="medium"):return _queued("programmer_model_forbidden")
        if emergency_effort not in {"medium","high"}:return _queued("programmer_emergency_effort_forbidden")
        dedicated_worker = ("codex-programmer/"+dedicated_model, dedicated_effort)
        emergency_worker = (EMERGENCY_TERRA[0], emergency_effort)
        regular = [GROK_MEDIUM]
        if programmer_account: regular.append(dedicated_worker)
        if gemini_enabled and gemini1_enabled: regular.append(GEMINI_HIGH)
        if gemini_enabled and gemini3_enabled: regular.append(GEMINI_NEW2_HIGH)
        if gemini_enabled and gemini2_enabled: regular.append(GEMINI2_HIGH)
        if sonnet_enabled: regular.append((ANTIGRAVITY_SONNET_KEY, "medium"))
        if emergency_original:
            # Regular contractors keep their route until exhausted. Only the
            # emergency original account yields while it still has quota.
            for pair in regular:
                if previous_key == pair[0] and effective[quota_key(pair[0])]['status'] not in {'exhausted','recovery_due'}:
                    return _chosen(pair, 'programmer_keep_regular_until_exhausted')
            if previous_key == EMERGENCY_TERRA[0]:
                for pair in regular:
                    if effective[quota_key(pair[0])]['status'] == 'available':
                        return _chosen(pair, 'programmer_return_from_emergency_positive_quota')
                # recovery_due permits an existing bounded Gemini recovery probe;
                # elapsed time is not recorded as positive quota evidence.
                if not any(effective[quota_key(pair[0])]['status']=='recovery_due' for pair in regular):
                    return _chosen(emergency_worker, 'programmer_emergency_waiting_regular_recovery') if codex == 'available' else _queued('programmer_accounts_exhausted')
        if grok != "exhausted":
            return _chosen(GROK_MEDIUM, "programmer_primary_grok_medium")
        if programmer_account and effective["codex-programmer"]["status"] != "exhausted":
            return _chosen(dedicated_worker, "programmer_dedicated_"+dedicated_model+"_"+dedicated_effort)
        if gemini_enabled and gemini1_enabled and effective["antigravity"]["status"] != "exhausted":
            return _chosen(GEMINI_HIGH, "programmer_fallback_gemini_high")
        if gemini_enabled and gemini3_enabled and effective["antigravity3"]["status"] != "exhausted":
            return _chosen(GEMINI_NEW2_HIGH, "programmer_fallback_gemini_account2_high")
        if gemini_enabled and gemini2_enabled and effective["antigravity2"]["status"] != "exhausted":
            return _chosen(GEMINI2_HIGH, "programmer_fallback_gemini_account3_high")
        if sonnet_enabled and effective[ANTIGRAVITY_SONNET_KEY]['status'] != 'exhausted':
            return _chosen((ANTIGRAVITY_SONNET_KEY, 'medium'), 'programmer_fallback_antigravity_sonnet_medium')
        if emergency_original and codex == 'available' and all(effective[quota_key(pair[0])]['status']=='exhausted' for pair in regular):
            return _chosen(emergency_worker, 'programmer_emergency_original_terra_'+emergency_effort)
        if programmer_account:
            return _queued("programmer_accounts_exhausted")
        if codex != "exhausted":
            return _chosen(SOL_MEDIUM, "programmer_fallback_sol_medium")
        return _queued("programmer_queued")
    if role == "reviewer":
        if claude != "exhausted":
            return _chosen(SONNET_HIGH, "reviewer_primary_sonnet_high")
        if codex == "exhausted":
            if grok == "available" or (previous_key == GROK_HIGH[0] and grok != "exhausted"):
                return _chosen(GROK_HIGH, "reviewer_fallback_grok_high")
            return _queued("reviewer_queued")
        return _chosen(SOL_MEDIUM, "reviewer_fallback_sol_medium")
    return _queued("invalid_role")


def _chosen(pair, reason):
    model_key, effort = pair
    provider, _, model = model_key.partition("/")
    if "astra" in model_key and not (provider == "codex" and effort == "medium"):
        return _queued("manager_queued")
    return {
        "model_key": model_key,
        "provider": provider,
        "model": model,
        "thinking_option": effort,
        "wait": False,
        "reason": reason,
    }


def _queued(reason):
    return {
        "model_key": None,
        "provider": None,
        "model": None,
        "thinking_option": None,
        "wait": True,
        "reason": reason,
    }


def _accept(working, provider, status, observed_at, reason):
    """Keep the newest known fact. Older or equal contrary evidence is dropped."""
    if status not in {"available", "exhausted"} or observed_at is None:
        return
    observations = working["observations"]
    current = observations.get(provider)
    if not isinstance(current, dict):
        current = {}
    watermark = _number(current.get("observed_at"))
    positive_at = _number(current.get("positive_at"))
    if watermark is not None and observed_at < watermark:
        return
    if watermark is not None and observed_at == watermark:
        if current.get("status") == status:
            return
        return
    if status == "exhausted" and positive_at is not None and observed_at <= positive_at:
        return
    updated = {
        "status": status,
        "observed_at": observed_at,
        "positive_at": observed_at if status == "available" else positive_at,
        "reason": reason if status == "exhausted" else None,
    }
    observations[provider] = updated
    if status == "available":
        working["exhaustions"].pop(provider, None)
        working["blocks"].pop(provider, None)
        return
    text = reason or "quota exhausted"
    working["exhaustions"][provider] = {"at": observed_at, "reason": text}
    working["blocks"][provider] = {"status": "exhausted", "at": observed_at, "reason": text}


def _ensure_observations(working):
    if not isinstance(working.get("observations"), dict):
        working["observations"] = {}
    exhaustions = working.get("exhaustions")
    if not isinstance(exhaustions, dict):
        exhaustions = {}
    for name, record in list(exhaustions.items()):
        if name not in OBSERVATION_KEYS or not isinstance(record, dict):
            continue
        at = _number(record.get("at"))
        if at is None:
            continue
        current = working["observations"].get(name)
        watermark = _number(current.get("observed_at")) if isinstance(current, dict) else None
        positive_at = _number(current.get("positive_at")) if isinstance(current, dict) else None
        if positive_at is not None and at <= positive_at:
            continue
        if watermark is not None and at <= watermark:
            continue
        working["observations"][name] = {
            "status": "exhausted",
            "observed_at": at,
            "positive_at": positive_at,
            "reason": record.get("reason"),
        }


def _effective(working):
    result = {}
    for name in OBSERVATION_KEYS:
        current = working["observations"].get(name)
        if (
            isinstance(current, dict)
            and current.get("status") in {"available", "exhausted"}
            and _number(current.get("observed_at")) is not None
        ):
            result[name] = {"status": current["status"], "observed_at": float(current["observed_at"])}
        else:
            result[name] = {"status": "unknown", "observed_at": None}
    return result


def _classify_catalog(catalog, now, max_age, minimum):
    found = {name: [] for name in OBSERVATION_KEYS}
    for model in _models(catalog):
        provider = _provider_name(quota_key(str(model.get("provider"))+"/"+str(model.get("id"))))
        if provider is None:
            continue
        found[provider].append(_classify_model(model, now, max_age, minimum))
    return {name: _reduce_provider(found[name]) for name in OBSERVATION_KEYS}


def _reduce_provider(observations):
    known = [item for item in observations if item["status"] in {"available", "exhausted"}]
    if not known:
        observed = [item["observed_at"] for item in observations if item["observed_at"] is not None]
        return {"status": "unknown", "observed_at": max(observed) if observed else None, "reason": None}
    known.sort(key=lambda item: (item["observed_at"], item["status"] == "exhausted"))
    return known[-1]


def _classify_model(model, now, max_age, minimum):
    quota = model.get("quota") if isinstance(model.get("quota"), dict) else {}
    observed = _timestamp(quota.get("observed_at"))
    source = quota.get("source")
    fresh = bool(source) and _is_fresh(observed, now, max_age)
    authenticated = model.get("authenticated") is True
    message = _quota_message(model, quota)
    status_name = str(quota.get("status") or "").strip().lower()
    if not fresh or not authenticated or status_name in (_NON_QUOTA_STATUS - _GENERIC_ERROR_STATUS):
        return {"status": "unknown", "observed_at": observed, "reason": None}
    if message and (_TRANSPORT_OR_AUTH.search(message) or _SLOT_ONLY.search(message)):
        return {"status": "unknown", "observed_at": observed, "reason": None}
    if explicit_quota_text(message):
        return {"status": "exhausted", "observed_at": observed, "reason": message.strip()}
    if status_name in _NON_QUOTA_STATUS:
        return {"status": "unknown", "observed_at": observed, "reason": None}
    windows = quota.get("windows")
    if not isinstance(windows, list) or not windows:
        windows = [quota]
    relevant = [window for window in windows if isinstance(window, dict)]
    exhausted = status_name == "exhausted"
    unknown_window = False
    for window in relevant:
        marker = str(window.get("status") or "").strip().lower()
        fraction = _fraction(window.get("remaining_fraction"))
        if marker == "exhausted" or fraction == 0:
            exhausted = True
            continue
        if marker in _NON_QUOTA_STATUS or fraction is None or fraction < minimum:
            unknown_window = True
    if exhausted:
        return {"status": "exhausted", "observed_at": observed, "reason": "quota exhausted"}
    if model.get("provider") in {"antigravity", "antigravity2", "antigravity3"} and source == "official agy response" and status_name == "available" and (model.get("cost") or {}).get("verified") is True:
        return {"status": "available", "observed_at": observed, "reason": None}
    if not relevant or unknown_window:
        return {"status": "unknown", "observed_at": observed, "reason": None}
    cost = model.get("cost") if isinstance(model.get("cost"), dict) else {}
    additional = _number(cost.get("additional_cost"))
    if cost.get("verified") is not True or additional != 0:
        return {"status": "unknown", "observed_at": observed, "reason": None}
    return {"status": "available", "observed_at": observed, "reason": None}


def _quota_message(model, quota):
    parts = [quota.get("error"), quota.get("message"), model.get("last_error"), model.get("error")]
    return " ".join(str(part) for part in parts if part)


def _models(catalog):
    if isinstance(catalog, list):
        models = catalog
    elif isinstance(catalog, dict):
        models = catalog.get("models") or []
    else:
        models = []
    for model in models:
        if isinstance(model, dict):
            yield model


def _settings(limits):
    limits = limits if isinstance(limits, dict) else {}
    policy = limits.get("runtime_policy") if isinstance(limits.get("runtime_policy"), dict) else {}
    supervision = limits.get("supervision") if isinstance(limits.get("supervision"), dict) else {}
    review = limits.get("review") if isinstance(limits.get("review"), dict) else {}
    max_age = _number(policy.get("quota_max_age_seconds"))
    if max_age is None:
        max_age = _number(supervision.get("quota_max_age_seconds"))
    if max_age is None:
        max_age = _number(review.get("quota_max_age_seconds"))
    if max_age is None or max_age < 0:
        max_age = DEFAULT_MAX_AGE
    minimum = _number(policy.get("return_min_remaining_fraction"))
    if minimum is None:
        minimum = _number(supervision.get("return_min_remaining_fraction"))
    if minimum is None or minimum < 0 or minimum > 1:
        minimum = DEFAULT_MIN_REMAINING
    return float(max_age), float(minimum)


def _blank_state(state):
    base = copy.deepcopy(state) if isinstance(state, dict) else {}
    base["version"] = 1
    if not isinstance(base.get("exhaustions"), dict):
        base["exhaustions"] = {}
    if not isinstance(base.get("blocks"), dict):
        base["blocks"] = {}
    if not isinstance(base.get("decisions"), dict):
        base["decisions"] = {}
    if not isinstance(base.get("observations"), dict):
        base["observations"] = {}
    return base


def _provider_name(value):
    text = str(value or "").strip().lower()
    if text == ANTIGRAVITY_SONNET_KEY:
        return text
    if "/" in text:
        text = text.split("/", 1)[0]
    if text in PROVIDERS:
        return text
    return None


def _moment(now):
    moment = _timestamp(now)
    if moment is None:
        return datetime.datetime.now(datetime.timezone.utc).timestamp()
    return moment


def _timestamp(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            pass
        try:
            parsed = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.timestamp()
    return None


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _fraction(value):
    number = _number(value)
    if number is None or number < 0 or number > 1:
        return None
    return number


def _is_fresh(observed, now, max_age):
    if observed is None:
        return False
    age = now - observed
    return 0 <= age <= max_age
