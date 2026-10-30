"""Evidence-aware, zero-additional-cost model selection (Python standard library).

No built-in model rankings. Catalog entries must be supplied by authenticated
provider discovery. All numeric priors below are explicitly policy assumptions,
not benchmark results or inferred account balances.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

DEFAULT_POLICY = {
    "weights": {"capability": 0.40, "success": 0.25, "latency": 0.10,
                "quota": 0.10, "diversity": 0.10, "economy": 0.05},
    "unknown_prior": 0.5,
    "history_prior_strength": 2,
    "reference_latency_seconds": 120,
    "catalog_max_age_seconds": 86400,
    "quota_max_age_seconds": 900,
    "max_concurrent_per_model": 20,
    "max_concurrent_per_provider": 20,
    "allowed_cost_kinds": ["subscription", "free"],
    "require_cost_source": True,
    "require_authenticated": True,
    "minimum_remaining_fraction": 0.01,
    "critical_min_observations": 3,
    "critical_min_success_rate": 0.6,
}


def model_key(model: dict) -> str:
    return f"{model['provider']}/{model['id']}"


def _time(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _fraction(value: Any) -> float | None:
    result = _number(value)
    return result if result is not None and 0 <= result <= 1 else None


def _age(value: Any, now: float) -> float | None:
    timestamp = _time(value)
    return max(0.0, now - timestamp) if timestamp is not None else None


def _evidence(value: Any, now: float) -> dict:
    """A bare numeric score is not evidence: it needs provenance."""
    if not isinstance(value, dict) or not value.get("source"):
        return {"value": None, "source": None, "age_seconds": None, "confidence": "unknown"}
    return {"value": _fraction(value.get("value")), "source": value["source"],
            "age_seconds": _age(value.get("observed_at"), now),
            "confidence": value.get("confidence", "unspecified")}


def select_model(catalog: dict | list, task: dict, history: dict | None = None,
                 active_models: dict | list | None = None, policy: dict | None = None,
                 now: float | str | None = None) -> dict:
    """Return selected candidate, eligible ranking and reasons for each rejection.

    history maps provider/model to {successes, failures, latency_seconds,
    observed_at}. active_models is a mapping provider/model -> active run count
    or a list of model keys. task supports specialty, difficulty (1..5),
    required_provider, excluded_models, allowed_models, min_context_tokens and
    criticality='high'. Caller must atomically reserve capacity after selecting.
    """
    from .model_limits import allowed_model,load_limits
    model_limits=load_limits()
    rules = {**DEFAULT_POLICY, **(policy or {})}
    rules["weights"] = {**DEFAULT_POLICY["weights"], **(policy or {}).get("weights", {})}
    timestamp = _time(now) if now is not None else datetime.now(timezone.utc).timestamp()
    if timestamp is None:
        raise ValueError("Invalid current timestamp")
    prior = _fraction(rules["unknown_prior"])
    if prior is None:
        raise ValueError("unknown_prior must be between zero and one")
    weights = rules["weights"]
    if any(_number(value) is None or value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Routing weights must be nonnegative with a positive sum")
    if rules["history_prior_strength"] <= 0 or rules["reference_latency_seconds"] <= 0:
        raise ValueError("Prior strength and reference latency must be positive")
    models = catalog.get("models", []) if isinstance(catalog, dict) else catalog
    catalog_observed = catalog.get("observed_at") if isinstance(catalog, dict) else None
    history = history or {}
    if isinstance(active_models, list):
        active = {key: active_models.count(key) for key in set(active_models)}
    else:
        active = active_models or {}
    provider_load: dict[str, int] = {}
    for key, count in active.items():
        provider = key.split("/", 1)[0]
        provider_load[provider] = provider_load.get(provider, 0) + max(0, int(count))

    rejected, ranking = [], []
    seen = set()
    specialty = str(task.get("specialty", "coding"))
    for model in models:
        reasons = []
        if not isinstance(model, dict) or not model.get("id") or not model.get("provider"):
            rejected.append({"key": None, "reasons": ["invalid_catalog_entry"]})
            continue
        key = model_key(model)
        if not allowed_model(model['provider'],model['id'],model_limits):
            reasons.append('explicit_user_model_limit')
        if key in seen:
            rejected.append({"key": key, "reasons": ["duplicate_catalog_entry"]})
            continue
        seen.add(key)
        if model.get("available") is not True:
            reasons.append("provider_or_model_unavailable_or_unknown")
        if rules["require_authenticated"] and model.get("authenticated") is not True:
            reasons.append("authentication_not_verified")
        age = _age(model.get("observed_at", catalog_observed), timestamp)
        if age is None or age > rules["catalog_max_age_seconds"]:
            reasons.append("catalog_missing_timestamp_or_stale")
        cost = model.get("cost") or {}
        if (cost.get("verified") is not True or cost.get("kind") not in rules["allowed_cost_kinds"]
                or _number(cost.get("additional_cost")) != 0):
            reasons.append("zero_additional_cost_not_verified")
        if rules["require_cost_source"] and not cost.get("source"):
            reasons.append("cost_provenance_missing")
        if task.get("required_provider") and model["provider"] != task["required_provider"]:
            reasons.append("provider_not_permitted_for_task")
        if task.get("allowed_models") is not None and key not in task["allowed_models"]:
            reasons.append("model_not_on_task_allowlist")
        if key in task.get("excluded_models", []):
            reasons.append("excluded_by_task_or_previous_failure")
        if model.get("restrictions", {}).get("allowed") is False:
            reasons.append("integration_restriction")
        if active.get(key, 0) >= model.get("max_concurrent", rules["max_concurrent_per_model"]):
            reasons.append("model_concurrency_limit")
        if provider_load.get(model["provider"], 0) >= rules["max_concurrent_per_provider"]:
            reasons.append("provider_concurrency_limit")
        cooldown = _time(model.get("retry_after"))
        if cooldown is not None and cooldown > timestamp:
            reasons.append("model_in_cooldown")
        min_context = task.get("min_context_tokens")
        context_tokens = _number(model.get("context_tokens"))
        if min_context and (context_tokens is None or context_tokens < min_context):
            reasons.append("required_context_unverified_or_insufficient")

        quota = model.get("quota") or {}
        quota_age = _age(quota.get("observed_at"), timestamp)
        quota_source = quota.get("source")
        windows = quota.get("windows") or [quota]
        remaining = []
        for window in windows:
            fraction = _fraction(window.get("remaining_fraction"))
            # Known exhaustion remains blocked until refreshed. An elapsed reset
            # timestamp is not evidence that the account balance was replenished.
            if window.get("status") == "exhausted" or fraction == 0:
                reasons.append("quota_exhausted_refresh_required")
            if fraction is not None and quota_source and quota_age is not None and quota_age <= rules["quota_max_age_seconds"]:
                remaining.append(fraction)
        quota_fraction = min(remaining) if remaining else None
        if quota_fraction is not None and quota_fraction < rules["minimum_remaining_fraction"]:
            reasons.append("quota_below_reserve")
        record = history.get(key) or {}
        successes = max(0, int(record.get("successes", 0)))
        failures = max(0, int(record.get("failures", 0)))
        observations = successes + failures
        if (task.get("criticality") == "high" and not task.get("exclusive_by_policy") and observations >= rules["critical_min_observations"]
                and successes / observations < rules["critical_min_success_rate"]):
            reasons.append("observed_reliability_below_critical_threshold")
        if reasons:
            rejected.append({"key": key, "provider": model["provider"], "id": model["id"], "reasons": sorted(set(reasons))})
            continue

        capability = _evidence(model.get("capabilities", {}).get(specialty), timestamp)
        if capability["value"] is None and specialty != "coding":
            general = _evidence(model.get("capabilities", {}).get("coding"), timestamp)
            if general["value"] is not None:
                capability = {**general, "fallback_specialty": "coding"}
        # Higher difficulty increases the weight of documented reasoning ability.
        difficulty = task.get("difficulty", 3)
        if isinstance(difficulty, str):
            difficulty = {"easy": 1, "medium": 3, "hard": 5}.get(difficulty, 3)
        difficulty = max(1, min(5, float(difficulty)))
        reasoning = _evidence(model.get("capabilities", {}).get("reasoning"), timestamp)
        capability_score = capability["value"] if capability["value"] is not None else prior
        if difficulty >= 4 and reasoning["value"] is not None:
            capability_score = 0.6 * capability_score + 0.4 * reasoning["value"]
        success_score = (successes + prior * rules["history_prior_strength"]) / (observations + rules["history_prior_strength"])
        latency = _number(record.get("latency_seconds"))
        if latency is None:
            latency = _number(model.get("latency_seconds"))
        latency_score = (rules["reference_latency_seconds"] / (rules["reference_latency_seconds"] + latency)
                         if latency is not None and latency >= 0 else prior)
        diversity = 1 / (1 + provider_load.get(model["provider"], 0) + active.get(key, 0))
        # Economic priority is an operator policy (not a benchmark); only relevant
        # once every candidate has passed the hard zero-additional-cost gate.
        economy = _fraction(model.get("economy_priority"))
        components = {
            "capability": capability_score, "success": success_score,
            "latency": latency_score, "quota": quota_fraction if quota_fraction is not None else prior,
            "diversity": diversity, "economy": economy if economy is not None else prior,
        }
        score = sum(weights[name] * value for name, value in components.items()) / sum(weights.values())
        ranking.append({
            "key": key, "provider": model["provider"], "id": model["id"],
            "mode": model.get("mode"), "score": round(score, 6), "components": components,
            "reasons": ["authenticated_available_model", "zero_additional_cost_verified",
                        "highest_configured_weighted_score_among_eligible_candidates"],
            "evidence": {
                "catalog": {"source": model.get("source"), "age_seconds": age},
                "capability": capability, "reasoning": reasoning,
                "history": {"successes": successes, "failures": failures, "observations": observations,
                            "success_rate": successes / observations if observations else None,
                            "source": "local_task_outcomes" if observations else None,
                            "age_seconds": _age(record.get("observed_at"), timestamp)},
                "latency_seconds": latency,
                "quota": {"remaining_fraction": quota_fraction, "source": quota_source,
                          "age_seconds": quota_age, "status": "known" if quota_fraction is not None else "unknown",
                          "resets_at": quota.get("resets_at")},
                "cost": {"kind": cost["kind"], "source": cost.get("source"), "additional_cost": 0},
            },
            "unknown_prior_applied_to": [name for name, value in [
                ("capability", capability["value"]), ("history", observations or None),
                ("latency", latency), ("quota", quota_fraction), ("economy", economy)] if value is None],
        })
    ranking.sort(key=lambda item: (-item["score"], item["key"]))
    for index, candidate in enumerate(ranking):
        candidate["rank"] = index + 1
        if index:
            candidate["reasons"][-1] = "eligible_but_lower_score_or_deterministic_tiebreak"
    return {
        "selected": ranking[0] if ranking else None, "ranking": ranking, "rejected": rejected,
        "policy": {"weights": weights, "unknown_prior": prior,
                   "prior_is_policy_assumption_not_benchmark": True, "additional_cost_budget": 0},
        "observed_at": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        "reason": "selected" if ranking else "no_eligible_model",
    }


def _models_by_key(catalog):
    models = catalog.get("models", []) if isinstance(catalog, dict) else catalog
    return {model_key(model): model for model in models if isinstance(model, dict) and model.get("provider") and model.get("id")}


def _fresh_quota(model, now, max_age):
    """Confirmed quota evidence only. Stale, unsourced or clock-only data is not proof."""
    if not isinstance(model, dict) or now is None:
        return None, None
    quota = model.get("quota") or {}
    observed = _time(quota.get("observed_at"))
    if not quota.get("source") or observed is None:
        return None, None
    age = now - observed
    if age < 0 or age > max_age:
        return None, None
    windows = quota.get("windows") or [quota]
    return windows, observed


def quota_exhausted(model, now, max_age):
    windows, _observed = _fresh_quota(model, now, max_age)
    if not windows:
        return False
    return any(window.get("status") == "exhausted" or _fraction(window.get("remaining_fraction")) == 0
               for window in windows)


def quota_available(model, now, max_age, minimum, newer_than=0):
    windows, observed = _fresh_quota(model, now, max_age)
    if not windows or not isinstance(model, dict):
        return False
    if newer_than and not observed > newer_than:
        return False
    if model.get("authenticated") is not True or model.get("available") is not True:
        return False
    cost = model.get("cost") or {}
    if cost.get("verified") is not True or _number(cost.get("additional_cost")) != 0:
        return False
    fractions = [window.get("remaining_fraction") for window in windows]
    if not fractions or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1
                                for value in fractions):
        return False
    if any(window.get("status") == "exhausted" or window.get("remaining_fraction") == 0 for window in windows):
        return False
    return min(fractions) >= minimum


def choose_review_role(limits, catalog, task, now):
    """Primary reviewer unless confirmed quota exhaustion authorizes the configured substitute.

    Difficulty, attempt, rank, concurrency and generic availability do not change role or effort.
    """
    review = limits.get("review") or {}
    primary = review.get("model")
    if not primary:
        return None, None
    if not review.get("fallback_allowed"):
        return "primary", primary
    fallback = review.get("fallback_model")
    max_age = review.get("quota_max_age_seconds", 300)
    minimum = review.get("return_min_remaining_fraction", 0.01)
    models = _models_by_key(catalog)
    route = task.get("reviewer_route") or {}
    state = route.get("state") or "primary"
    blocked_at = float(route.get("blocked_at") or 0)
    fallback_blocked_at = float(route.get("fallback_blocked_at") or 0)
    timestamp = _time(now) if now is not None else datetime.now(timezone.utc).timestamp()
    primary_back = (review.get("auto_return", True) and not route.get("hold_return") and
                    quota_available(models.get(primary), timestamp, max_age, minimum, blocked_at))
    held = state in {"fallback", "fallback_wait", "both_exhausted"}
    if held and primary_back:
        return "primary", primary
    if held and state == "both_exhausted":
        fallback_back = quota_available(models.get(fallback), timestamp, max_age, minimum, fallback_blocked_at)
        if fallback and fallback_back:
            return "fallback", fallback
        return None, None
    if held or quota_exhausted(models.get(primary), timestamp, max_age):
        if not fallback:
            return "primary", primary
        if quota_exhausted(models.get(fallback), timestamp, max_age):
            return None, None
        if state == "both_exhausted":
            return None, None
        return "fallback", fallback
    return "primary", primary


def select_review(catalog, task, history, active_models, policy, now, attempt, limits):
    from .model_limits import constrain_catalog, thinking_for
    review = limits.get("review") or {}
    role, key = choose_review_role(limits, catalog, task, now)
    if not key:
        primary = review.get("model")
        fallback = review.get("fallback_model")
        return {
            "selected": None, "ranking": [],
            "rejected": [{"key": item, "reasons": ["quota_exhausted_refresh_required"]}
                         for item in (primary, fallback) if item],
            "reason": "review_quota_waiting", "preference_reason": "review_quota_waiting",
        }
    provider = key.split("/", 1)[0]
    # Implementation allowlists and a hardcoded provider must not choose the reviewer.
    forced = {**task, "specialty": "review", "allowed_models": [key], "required_provider": provider,
              "review_role": role}
    constrained = constrain_catalog(catalog, forced)
    result = select_model(constrained, forced, history, active_models, policy, now)
    if not result["selected"]:
        return result
    entries = constrained.get("models", []) if isinstance(constrained, dict) else constrained
    models = _models_by_key({"models": entries})
    selected = result["selected"]
    selected["thinking_option_id"] = thinking_for(models[selected["key"]], forced, attempt, limits)
    reason = ("explicit_user_review_model_and_configured_effort" if role == "primary"
              else "review_quota_fallback_fixed_effort")
    for entry in result["ranking"]:
        entry["reasons"][-1] = reason if entry["key"] == selected["key"] else "eligible_not_selected_after_configured_preferences"
    result["selected"] = selected
    result["preference_reason"] = reason
    result["reason"] = reason
    return result


def select_for_task(catalog, task, history=None, active_models=None, policy=None, now=None,
                    attempt=0, previous_model=None, phase="implement"):
    """Shared preview/runtime selection: operator roles are preferences, not benchmarks."""
    from .model_limits import constrain_catalog,thinking_for,load_limits
    limits = load_limits()
    if limits.get('policy_engine') == 'proposed-2026-10-29':
        from .policy_integration import select_for_role
        return select_for_role(catalog, task, limits, now=now, phase=phase, state=task.get('policy_state'))
    if phase == 'review' or task.get('specialty') == 'review':
        return select_review(catalog, task, history, active_models, policy, now, attempt, limits)
    if phase == 'implement' and task.get('specialty', 'coding') in limits.get('programming', {}).get('specialties', []):
        # The user made this model the only programmer. A reliability threshold
        # cannot pick an alternative, so it would only stall the queue forever;
        # tests and the independent review still gate every result.
        task = {**task, 'allowed_models': [limits['programming']['model']], 'required_provider': limits['programming']['model'].split('/',1)[0], 'exclusive_by_policy': True}
    catalog=constrain_catalog(catalog,task)
    result = select_model(catalog, task, history, active_models, policy, now)
    if not result['selected']: return result
    entries = catalog.get('models', []) if isinstance(catalog, dict) else catalog
    models = {f"{m['provider']}/{m['id']}": m for m in entries}
    eligible = result['ranking']
    reason = 'weighted_evidence_score'
    difficulty = task.get('difficulty', 3)
    if isinstance(difficulty, str): difficulty = {'easy':1,'medium':3,'hard':5}.get(difficulty,3)
    if phase == 'implement' and attempt == 1:
        previous = [entry for entry in eligible if entry['key'] == previous_model]
        if previous: eligible = previous; reason = 'same_model_first_correction'
    if difficulty >= 4 or (phase == 'implement' and attempt >= 2):
        advanced = [entry for entry in eligible if models[entry['key']].get('tier') == 'advanced']
        if advanced: eligible = advanced; reason = 'configured_advanced_role_for_difficulty_or_escalation'
        else: reason = 'advanced_role_unavailable_permitted_fallback'
    specialty = task.get('specialty', 'coding')
    specialized = [entry for entry in eligible if specialty in models[entry['key']].get('preferred_specialties', [])]
    if specialized: eligible = specialized; reason += '+native_profile_specialty'
    preferences = load_limits().get('routing_preferences', {})
    category = 'complex' if float(difficulty) >= 4 else 'routine'
    if phase == 'implement' and specialty in preferences.get(category+'_specialties', []):
        preferred = [entry for entry in result['ranking'] if entry['key'] == preferences.get(category+'_model')]
        if preferred:
            eligible = preferred
            reason = 'explicit_user_'+category+'_model_preference'
    selected = eligible[0]
    if task.get('specialty') == 'review':
        reason = 'explicit_user_review_model_and_configured_effort'
    elif phase == 'implement' and specialty in limits.get('programming', {}).get('specialties', []):
        reason = 'explicit_user_programming_only_grok_medium'
    for entry in result['ranking']:
        entry['reasons'][-1] = reason if entry['key'] == selected['key'] else 'eligible_not_selected_after_configured_preferences'
    result['selected'] = selected
    selected['thinking_option_id']=thinking_for(models[selected['key']],task,attempt)
    result['preference_reason'] = reason
    result['reason'] = reason
    return result
