import copy
import json
from pathlib import Path
import tempfile
import time
import unittest

import orchestrator.model_limits as model_limits
from orchestrator.routing import select_for_task, select_model
from orchestrator.resources import assess_resources, sample_resources

ROOT = Path(__file__).resolve().parents[1]
model_limits.LIMITS_FILE = ROOT / '.maintenance-model-limits.json'
NEW_LIMITS = json.loads((ROOT / '.new-role-model-limits.json').read_text())


NOW = 1_800_000_000


def candidate(name="model-a", provider="provider-a"):
    # Synthetic model IDs are test fixtures only; production has no built-in IDs.
    return {
        "id": name, "provider": provider, "available": True, "authenticated": True,
        "observed_at": NOW, "source": "test_catalog",
        "cost": {"kind": "subscription", "verified": True, "additional_cost": 0, "source": "test_authentication"},
        "capabilities": {}, "quota": {},
    }


class RoutingTests(unittest.TestCase):
    def test_unknown_cost_is_never_fallback(self):
        first, second = candidate(), candidate("model-b")
        first["available"] = False
        second["cost"]["verified"] = False
        result = select_model([first, second], {}, now=NOW)
        self.assertIsNone(result["selected"])
        self.assertIn("zero_additional_cost_not_verified", result["rejected"][1]["reasons"])

    def test_paid_model_excluded_despite_high_quality(self):
        free, paid = candidate(), candidate("paid")
        paid["cost"].update(kind="api", additional_cost=0.01)
        paid["capabilities"] = {"coding": {"value": 1, "source": "benchmark"}}
        result = select_model([paid, free], {}, now=NOW)
        self.assertEqual(result["selected"]["id"], "model-a")

    def test_unknown_quota_remains_unknown_and_does_not_exclude(self):
        result = select_model([candidate()], {}, now=NOW)
        self.assertIsNotNone(result["selected"])
        evidence = result["selected"]["evidence"]["quota"]
        self.assertIsNone(evidence["remaining_fraction"])
        self.assertEqual(evidence["status"], "unknown")
        self.assertIn("quota", result["selected"]["unknown_prior_applied_to"])

    def test_exhausted_quota_stays_excluded_until_refresh(self):
        item = candidate()
        item["quota"] = {"source": "provider", "observed_at": NOW - 3600,
                         "status": "exhausted", "resets_at": NOW - 1}
        result = select_model([item], {}, now=NOW)
        self.assertIsNone(result["selected"])
        self.assertIn("quota_exhausted_refresh_required", result["rejected"][0]["reasons"])

    def test_multiple_quota_windows_use_tightest_limit(self):
        item = candidate()
        item["quota"] = {"source": "provider", "observed_at": NOW,
                         "windows": [{"remaining_fraction": 0.9}, {"remaining_fraction": 0}]}
        self.assertIsNone(select_model([item], {}, now=NOW)["selected"])

    def test_stale_quota_not_falsely_treated_as_current_balance(self):
        item = candidate()
        item["quota"] = {"source": "provider", "observed_at": NOW - 1000, "remaining_fraction": 1}
        selected = select_model([item], {}, now=NOW)["selected"]
        self.assertIsNone(selected["evidence"]["quota"]["remaining_fraction"])

    def test_missing_provenance_does_not_create_benchmark(self):
        item = candidate()
        item["capabilities"]["coding"] = 0.99
        selected = select_model([item], {}, now=NOW)["selected"]
        self.assertIsNone(selected["evidence"]["capability"]["value"])
        self.assertEqual(selected["components"]["capability"], 0.5)

    def test_specialty_and_reasoning_select_documented_suitable_model(self):
        plain, advanced = candidate(), candidate("model-b")
        plain["capabilities"] = {"backend": {"value": 0.6, "source": "local_evaluation"}, "reasoning": {"value": 0.2, "source": "local_evaluation"}}
        advanced["capabilities"] = {"backend": {"value": 0.6, "source": "local_evaluation"}, "reasoning": {"value": 0.9, "source": "local_evaluation"}}
        selected = select_model([plain, advanced], {"specialty": "backend", "difficulty": 5}, now=NOW)["selected"]
        self.assertEqual(selected["id"], "model-b")

    def test_historical_success_and_diversity_influence_choice(self):
        first, second = candidate(), candidate("model-b", "provider-b")
        history = {"provider-a/model-a": {"successes": 1, "failures": 5},
                   "provider-b/model-b": {"successes": 6, "failures": 0}}
        selected = select_model([first, second], {}, history=history,
                                active_models={"provider-a/model-a": 1}, now=NOW)["selected"]
        self.assertEqual(selected["provider"], "provider-b")
        self.assertEqual(selected["evidence"]["history"]["observations"], 6)

    def test_failed_model_excluded_and_fallback_stays_on_allowlist(self):
        first, second = candidate(), candidate("model-b", "provider-b")
        task = {"excluded_models": ["provider-a/model-a"], "allowed_models": ["provider-a/model-a", "provider-b/model-b"]}
        result = select_model([first, second], task, now=NOW)
        self.assertEqual(result["selected"]["key"], "provider-b/model-b")
        self.assertIn("excluded_by_task_or_previous_failure", result["rejected"][0]["reasons"])

    def test_unknown_context_cannot_satisfy_explicit_requirement(self):
        result = select_model([candidate()], {"min_context_tokens": 100000}, now=NOW)
        self.assertIsNone(result["selected"])

    def test_expired_catalog_and_unverified_auth_block(self):
        item = candidate()
        item["observed_at"] = NOW - 90000
        item["authenticated"] = None
        reasons = select_model([item], {}, now=NOW)["rejected"][0]["reasons"]
        self.assertIn("authentication_not_verified", reasons)
        self.assertIn("catalog_missing_timestamp_or_stale", reasons)


def review_model(model_id, provider):
    return {
        "id": model_id, "provider": provider, "available": True, "authenticated": True,
        "observed_at": NOW, "source": "fixture",
        "cost": {"kind": "subscription", "verified": True, "additional_cost": 0, "source": "fixture"},
        "capabilities": {"review": {"value": 0.1, "source": "fixture"}}, "quota": {},
        "safe_thinking_options": ["low", "medium", "high"], "tier": "advanced",
        "preferred_specialties": ["review"],
    }


class ReviewRoutingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.limits_patch = unittest.mock.patch('orchestrator.model_limits.load_limits', return_value=NEW_LIMITS)
        self.limits_patch.start()
        self.addCleanup(self.limits_patch.stop)
        self.sonnet = review_model('claude-sonnet-5-5', 'claude')
        self.sol = review_model('gpt-6.1-sol', 'codex')

    def test_primary_sonnet_stays_high_despite_difficulty_attempt_and_rank(self):
        weak = copy.deepcopy(self.sonnet)
        weak['capabilities'] = {'review': {'value': 0.01, 'source': 'fixture'}}
        strong = copy.deepcopy(self.sol)
        strong['capabilities'] = {'review': {'value': 1, 'source': 'fixture'}}
        for difficulty in (1, 3, 5):
            for attempt in (0, 1, 4):
                result = select_for_task([weak, strong], {'specialty': 'backend', 'difficulty': difficulty,
                                            'required_provider': 'opencode', 'allowed_models': ['grok/grok-4.7']},
                                          phase='review', attempt=attempt, now=NOW)
                self.assertEqual(result['selected']['key'], 'claude/claude-sonnet-5-5')
                self.assertEqual(result['selected']['thinking_option_id'], 'high')
                self.assertEqual(result['selected']['provider'], 'claude')

    def test_fallback_is_only_fresh_quota_and_always_sol_medium(self):
        blocked = copy.deepcopy(self.sonnet)
        blocked['quota'] = {'source': 'provider', 'observed_at': NOW,
                            'windows': [{'status': 'exhausted', 'remaining_fraction': 0}]}
        for difficulty, attempt in ((1, 0), (5, 4)):
            result = select_for_task([blocked, self.sol], {'specialty': 'review', 'difficulty': difficulty},
                                      phase='review', attempt=attempt, now=NOW)
            self.assertEqual(result['selected']['key'], 'codex/gpt-6.1-sol')
            self.assertEqual(result['selected']['thinking_option_id'], 'medium')
            self.assertEqual(result['reason'], 'review_quota_fallback_fixed_effort')

    def test_concurrency_auth_and_generic_unavailability_do_not_change_role(self):
        busy = select_for_task([self.sonnet, self.sol], {'specialty': 'review', 'difficulty': 5}, phase='review',
                                attempt=4, active_models=['claude/claude-sonnet-5-5', 'claude/claude-sonnet-5-5'], now=NOW)
        self.assertIsNone(busy['selected'])
        self.assertIn('model_concurrency_limit', busy['rejected'][0]['reasons'])
        unauthenticated = copy.deepcopy(self.sonnet)
        unauthenticated['authenticated'] = False
        self.assertIsNone(select_for_task([unauthenticated, self.sol], {'specialty': 'review'}, phase='review', now=NOW)['selected'])
        down = copy.deepcopy(self.sonnet)
        down['available'] = False
        self.assertIsNone(select_for_task([down, self.sol], {'specialty': 'review'}, phase='review', now=NOW)['selected'])
        stale = copy.deepcopy(self.sonnet)
        stale['quota'] = {'source': 'provider', 'observed_at': NOW - 10000, 'windows': [{'remaining_fraction': 0}]}
        self.assertIsNone(select_for_task([stale, self.sol], {'specialty': 'review'}, phase='review', now=NOW)['selected'])

    def test_return_requires_newer_positive_quota_not_the_clock(self):
        route = {'state': 'fallback', 'blocked_at': NOW - 20, 'generation': 2}
        restored = copy.deepcopy(self.sonnet)
        restored['quota'] = {'source': 'provider', 'observed_at': NOW,
                             'windows': [{'remaining_fraction': 0.4}]}
        result = select_for_task([restored, self.sol], {'specialty': 'review', 'difficulty': 5, 'reviewer_route': route},
                                  phase='review', attempt=4, now=NOW)
        self.assertEqual(result['selected']['key'], 'claude/claude-sonnet-5-5')
        self.assertEqual(result['selected']['thinking_option_id'], 'high')
        old = copy.deepcopy(restored)
        old['quota']['observed_at'] = NOW - 40
        held = select_for_task([old, self.sol], {'specialty': 'review', 'reviewer_route': route}, phase='review', now=NOW)
        self.assertEqual(held['selected']['key'], 'codex/gpt-6.1-sol')
        self.assertEqual(held['selected']['thinking_option_id'], 'medium')
        unknown = copy.deepcopy(self.sonnet)
        still = select_for_task([unknown, self.sol], {'specialty': 'review', 'reviewer_route': route}, phase='review', now=NOW)
        self.assertEqual(still['selected']['key'], 'codex/gpt-6.1-sol')
        active = select_for_task([restored, self.sol], {'specialty': 'review', 'reviewer_route': {**route, 'hold_return': True}},
                                  phase='review', now=NOW)
        self.assertEqual(active['selected']['key'], 'codex/gpt-6.1-sol')

    def test_both_reviewers_exhausted_waits_without_a_third_model(self):
        sonnet, sol = copy.deepcopy(self.sonnet), copy.deepcopy(self.sol)
        for item in (sonnet, sol):
            item['quota'] = {'source': 'provider', 'observed_at': NOW, 'windows': [{'remaining_fraction': 0}]}
        result = select_for_task([sonnet, sol], {'specialty': 'review', 'difficulty': 5}, phase='review', attempt=4, now=NOW)
        self.assertIsNone(result['selected'])
        self.assertEqual(result['reason'], 'review_quota_waiting')

    def test_previous_policy_still_selects_configured_sol_without_fallback(self):
        old = json.loads((ROOT / '.maintenance-model-limits.json').read_text())
        with unittest.mock.patch('orchestrator.model_limits.load_limits', return_value=old):
            effort = old['review']['thinking_option']
            blocked = copy.deepcopy(self.sonnet)
            blocked['quota'] = {'source': 'provider', 'observed_at': NOW, 'windows': [{'remaining_fraction': 0}]}
            result = select_for_task([self.sol, blocked], {'specialty': 'review', 'difficulty': 5}, phase='review', attempt=4, now=NOW)
            self.assertEqual(result['selected']['key'], 'codex/gpt-6.1-sol')
            self.assertEqual(result['selected']['thinking_option_id'], effort)
            self.sonnet['quota'] = blocked['quota']
            self.assertIsNone(select_for_task([self.sonnet], {'specialty': 'review'}, phase='review', now=NOW)['selected'])


def healthy_sample():
    return {"sampled_at": NOW, "memory_available_mib": 2500, "disk_free_gib": 20,
            "disk_used_fraction": 0.8, "load_per_cpu": 0.2, "cpu_percent": 20,
            "swap_io_mib_per_second": 0.5, "swap_used_mib": 6000,
            "memory_psi": {"some": {"avg10": 0.1}}, "io_psi": {"some": {"avg10": 0.1}}}


class ResourceTests(unittest.TestCase):
    def test_two_workers_plus_supervisor_allowed_but_third_worker_queued(self):
        self.assertTrue(assess_resources(active_workers=1, supervisor_active=True, sample=healthy_sample(), now=NOW)["allowed"])
        blocked = assess_resources(active_workers=2, supervisor_active=True, sample=healthy_sample(), now=NOW)
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["action"], "keep_queued")
        self.assertIn("worker_limit_reached", blocked["reasons"])

    def test_available_memory_reserves_host_floor_and_one_new_worker(self):
        sample = healthy_sample()
        sample["memory_available_mib"] = 1437
        blocked = assess_resources(sample=sample, now=NOW)
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["required_available_mib_for_next_worker"], 1536)
        sample["memory_available_mib"] = 1536
        self.assertTrue(assess_resources(sample=sample, now=NOW)["allowed"])

    def test_swap_usage_alone_is_not_thrashing_but_swap_io_blocks(self):
        sample = healthy_sample()
        self.assertTrue(assess_resources(sample=sample, now=NOW)["allowed"])
        sample["swap_io_mib_per_second"] = 15
        self.assertIn("swap_churn_high", assess_resources(sample=sample, now=NOW)["reasons"])

    def test_memory_pressure_disk_and_cpu_guard(self):
        for field, value, reason in [
            ("memory_psi", {"some": {"avg10": 3}}, "memory_pressure_high"),
            ("disk_free_gib", 1, "insufficient_disk_space"),
            ("load_per_cpu", 2, "cpu_load_high"),
        ]:
            with self.subTest(field=field):
                sample = healthy_sample()
                sample[field] = value
                self.assertIn(reason, assess_resources(sample=sample, now=NOW)["reasons"])

    def test_missing_or_stale_sample_fails_closed(self):
        self.assertFalse(assess_resources(sample={}, now=NOW)["allowed"])
        sample = healthy_sample()
        sample["sampled_at"] -= 31
        self.assertFalse(assess_resources(sample=sample, now=NOW)["allowed"])

    def test_live_sample_is_read_only_and_exposes_unknown_initial_rates(self):
        with tempfile.TemporaryDirectory() as path:
            sample = sample_resources(disk_path=path)
        self.assertGreater(sample["memory_total_mib"], 0)
        self.assertIsNone(sample["cpu_percent"])
        self.assertIsNone(sample["swap_io_mib_per_second"])
        self.assertEqual(sample["source"], "local_linux_procfs")


if __name__ == "__main__":
    unittest.main()
