import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import orchestrator.model_limits as model_limits
from orchestrator import core, reviewer_routes

ROOT = Path(__file__).resolve().parents[1]
model_limits.LIMITS_FILE = ROOT / '.maintenance-model-limits.json'
NEW_LIMITS = ROOT / '.new-role-model-limits.json'


class ReviewerRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.repo = self.root / 'workspace' / 'repo'
        self.repo.mkdir(parents=True)
        self.clock = time.time()
        self.previous = model_limits.LIMITS_FILE
        model_limits.LIMITS_FILE = NEW_LIMITS
        for item in (
            patch.object(core, 'STATE', self.state),
            patch.object(core, 'DEV', self.root / 'workspace'),
            patch.object(core, 'now', side_effect=lambda: self.clock),
            patch.object(core, 'archive_worker'),
            patch('orchestrator.grok_usage.safe_subscription', return_value=True),
        ):
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(setattr, model_limits, 'LIMITS_FILE', self.previous)
        self.spec = json.dumps({'objective': 'review me', 'acceptance': ['ok'], 'allowed_files': ['module.py'],
                                'tests': [['python3', '-m', 'unittest']], 'timeout_seconds': 60})

    def insert(self, db, phase='review', state='running', attempt=2, review_model='claude/claude-sonnet-5-5',
               agent_id='rev-sonnet', error=None, digest='digest-under-review'):
        db.execute('''INSERT INTO jobs(id,objective,repo,branch,plan,plan_hash,state,supervisor_id,created,updated)
                      VALUES('job','objective',?,'orchestration/job','{}','job','running',NULL,?,?)''',
                   (str(self.repo), self.clock, self.clock))
        db.execute('''INSERT INTO tasks(id,job_id,task_key,spec,state,phase,attempt,model,review_model,agent_id,
                      cwd,workspace_id,review_digest,result,error,updated)
                      VALUES('task','job','first',?,?,?,?, 'grok/grok-4.7',?,?,?,?,?,?,?,?)''',
                   (self.spec, state, phase, attempt, review_model, agent_id, str(self.repo), 'workspace-1',
                    digest, '{"implementation":{"status":"completed"}}', error, self.clock))
        db.commit()
        return dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone())

    def catalog(self, sonnet_fraction=None, sol_fraction=None, sonnet_at=None, sol_at=None):
        def entry(provider, model_id, fraction, observed):
            quota = {}
            if fraction is not None:
                quota = {'source': 'fixture', 'observed_at': self.clock if observed is None else observed,
                         'windows': [{'remaining_fraction': fraction}]}
            return {'provider': provider, 'id': model_id, 'available': True, 'authenticated': True,
                    'observed_at': self.clock, 'source': 'fixture',
                    'cost': {'kind': 'subscription', 'verified': True, 'additional_cost': 0, 'source': 'fixture'},
                    'quota': quota, 'tier': 'advanced', 'preferred_specialties': ['review']}
        document = {'models': [entry('claude', 'claude-sonnet-5-5', sonnet_fraction, sonnet_at),
                               entry('codex', 'gpt-6.1-sol', sol_fraction, sol_at)]}
        (self.state / 'catalog.json').write_text(json.dumps(document))
        return document

    def test_session_quota_persists_across_restart_without_programmer_defect(self):
        with core.database() as db:
            task = self.insert(db)
            self.assertTrue(reviewer_routes.note_session_quota(db, task, "You've hit your session limit", 'explicit_limit'))
            self.assertTrue(reviewer_routes.note_session_quota(db, dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone()),
                                                               "You've hit your session limit"))
        with core.database() as db:
            row = dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone())
            route = reviewer_routes.current_route(db)
            event = json.loads(db.execute("SELECT data FROM events WHERE kind='reviewer_substituted'").fetchone()['data'])
            self.assertEqual(db.execute('SELECT count(*) FROM outcomes').fetchone()[0], 0)
        self.assertEqual(row['phase'], 'review')
        self.assertEqual(row['state'], 'queued')
        self.assertEqual(row['attempt'], 2)
        self.assertEqual(row['review_digest'], 'digest-under-review')
        self.assertEqual(row['model'], 'grok/grok-4.7')
        self.assertIsNone(row['agent_id'])
        self.assertIsNone(row['launch_request'])
        self.assertTrue(row['error'].startswith('reviewer_quota:'))
        self.assertEqual(route['state'], 'fallback')
        self.assertEqual(route['active_model'], 'codex/gpt-6.1-sol')
        self.assertEqual(route['generation'], 1)
        self.assertEqual(event['evidence'], 'explicit_limit')
        self.assertEqual(event['to_thinking'], 'medium')
        self.assertEqual(event['attempt'], 2)
        self.assertEqual(event['programmer_model'], 'grok/grok-4.7')
        self.assertIn('session limit', event['reason'])

    def test_explicit_and_catalog_evidence_switch_but_auth_transport_slot_and_real_review_do_not(self):
        catalog = self.catalog(sonnet_fraction=0)
        task = {'id': 'task', 'phase': 'review', 'review_model': 'claude/claude-sonnet-5-5', 'attempt': 2}
        calls = []
        def bridge(action, **kwargs):
            calls.append(action)
            if action == 'timeline':
                return {'entries': [{'timestamp': self.clock, 'item': {'type': 'error', 'message': "You've hit your session limit"}}]}
            raise AssertionError(action)
        with patch.object(core, 'bridge', side_effect=bridge):
            self.assertEqual(reviewer_routes.quota_failure_reason(task, {'lastError': "You've hit your session limit"}), 'explicit_limit')
            self.assertEqual(reviewer_routes.quota_failure_reason(task, {'lastError': "You've hit your limit"}), 'explicit_limit')
            self.assertEqual(reviewer_routes.quota_failure_reason(task, {'lastError': 'You have hit your session limit'}), 'explicit_limit')
            self.assertEqual(reviewer_routes.quota_failure_reason(task, {'lastError': 'rate_limit_error: usage limit reached'}), 'explicit_limit')
            self.assertEqual(reviewer_routes.quota_failure_reason(task, {'id': 'rev', 'attentionReason': 'error', 'lastError': 'provider stopped'}), 'explicit_limit')
            self.assertEqual(calls, ['timeline'])
            for message in ('Authentication required', 'transport error: connection reset', 'no available slot',
                            'rate_limit_error: too many requests',
                            'network timeout while reading usage_limit response',
                            'Authentication required: hit your session limit',
                            'concurrency limit while quota exceeded',
                            'timeout reading session limit',
                            'Revisão reprovou: missing case', 'Regressão após revisão: changed', 'Testes falharam: expected'):
                self.assertIsNone(reviewer_routes.quota_failure_reason(
                    task, {'id': 'rev', 'attentionReason': 'error', 'lastError': message}, catalog), message)
            self.assertEqual(calls, ['timeline'])
            self.assertEqual(reviewer_routes.quota_failure_reason(task, {'lastError': 'provider stopped'}, catalog), 'catalog')
        model_limits.LIMITS_FILE = ROOT / '.maintenance-model-limits.json'
        self.assertIsNone(reviewer_routes.quota_failure_reason(task, {'lastError': "You've hit your session limit"}, catalog))

    def test_return_requires_newer_quota_and_idle_reviewer_without_polling(self):
        self.catalog(sonnet_fraction=0.4, sonnet_at=self.clock)
        with core.database() as db:
            task = self.insert(db, state='queued', agent_id=None)
            reviewer_routes.note_session_quota(db, task, "You've hit your session limit")
            route = reviewer_routes.current_route(db)
            self.clock += 5
            with patch.object(core, 'bridge', side_effect=AssertionError('model poll')):
                reviewer_routes.consider_return(db, json.loads((self.state/'catalog.json').read_text()))
            self.assertEqual(reviewer_routes.current_route(db)['state'], 'fallback')
            self.catalog(sonnet_fraction=0.4, sonnet_at=route['blocked_at'])
            reviewer_routes.consider_return(db, json.loads((self.state/'catalog.json').read_text()))
            self.assertEqual(reviewer_routes.current_route(db)['state'], 'fallback')
            self.catalog(sonnet_fraction=0.4, sonnet_at=self.clock)
            db.execute("UPDATE tasks SET state='running', agent_id='rev-sol', review_model='codex/gpt-6.1-sol' WHERE id='task'")
            db.commit()
            reviewer_routes.consider_return(db, json.loads((self.state/'catalog.json').read_text()))
            self.assertEqual(reviewer_routes.current_route(db)['state'], 'fallback')
            db.execute("UPDATE tasks SET state='queued', agent_id=NULL WHERE id='task'")
            db.commit()
            reviewer_routes.consider_return(db, json.loads((self.state/'catalog.json').read_text()))
            restored = reviewer_routes.current_route(db)
            event = json.loads(db.execute("SELECT data FROM events WHERE kind='reviewer_returned'").fetchone()['data'])
        self.assertEqual(restored['state'], 'primary')
        self.assertEqual(restored['active_model'], 'claude/claude-sonnet-5-5')
        self.assertEqual(event['reason'], 'newer_positive_quota')
        self.assertGreater(event['evidence_at'], event['blocked_at'])

    def test_both_exhausted_waits_and_substitute_can_resume_without_a_new_executor(self):
        with core.database() as db:
            task = self.insert(db)
            reviewer_routes.note_session_quota(db, task, "You've hit your session limit")
            db.execute("UPDATE tasks SET state='running', agent_id='rev-sol', review_model='codex/gpt-6.1-sol' WHERE id='task'")
            db.commit()
            running = dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone())
            reviewer_routes.note_session_quota(db, running, "You've hit your session limit", 'explicit_limit')
            row = dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone())
            route = reviewer_routes.current_route(db)
        self.assertEqual(route['state'], 'both_exhausted')
        self.assertEqual(route['generation'], 2)
        self.assertEqual(row['phase'], 'review')
        self.assertEqual(row['attempt'], 2)
        self.assertEqual(row['review_digest'], 'digest-under-review')
        self.assertIsNone(row['agent_id'])
        self.assertGreater(row['retry_at'], self.clock)
        calls = []
        self.catalog(sonnet_fraction=0, sol_fraction=0)
        with patch.object(core, 'bridge', side_effect=lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError('executor'))), \
             patch.object(core, 'assess_resources', return_value={'allowed': True, 'reasons': []}), \
             patch.object(core, 'native_snapshot', side_effect=AssertionError('snapshot')):
            core.tick()
            self.assertEqual(calls, [])
            self.clock += 61
            core.tick()
        with core.database() as db:
            waited = dict(db.execute("SELECT phase,attempt,review_digest,state,model FROM tasks WHERE id='task'").fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM outcomes').fetchone()[0], 0)
            self.assertEqual(reviewer_routes.current_route(db)['state'], 'both_exhausted')
        self.assertEqual(calls, [])
        self.assertEqual(waited['phase'], 'review')
        self.assertEqual(waited['attempt'], 2)
        self.assertEqual(waited['review_digest'], 'digest-under-review')
        self.assertEqual(waited['model'], 'grok/grok-4.7')
        self.catalog(sol_fraction=0.5, sol_at=self.clock)
        with patch.object(core, 'bridge', side_effect=AssertionError('model poll')):
            with core.database() as db:
                reviewer_routes.consider_return(db, json.loads((self.state/'catalog.json').read_text()))
                self.assertEqual(reviewer_routes.current_route(db)['state'], 'fallback')
                resumed = json.loads(db.execute("SELECT data FROM events WHERE kind='reviewer_fallback_resumed'").fetchone()['data'])
        self.assertEqual(resumed['model'], 'codex/gpt-6.1-sol')
        self.assertEqual(resumed['thinking'], 'medium')

    def test_launch_exception_switches_reviewer_and_preserves_artifact(self):
        self.catalog()
        (self.repo/'.paseo-result.json').write_text('{"status":"completed","summary":"implemented"}')
        (self.repo/'.paseo-review.json').write_text('{"decision":"fail"}')
        calls = []
        def bridge(action, **kwargs):
            calls.append((action, kwargs.get('options', {})))
            if len([item for item in calls if item[0] == 'agent-create']) == 1:
                raise RuntimeError("You've hit your session limit")
            return {'id': 'rev-sol'}
        with core.database() as db, patch.object(core, 'bridge', side_effect=bridge):
            task = self.insert(db, state='queued', agent_id=None)
            job = dict(db.execute("SELECT * FROM jobs WHERE id='job'").fetchone())
            core.launch(db, task, job, [])
            queued = dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone())
            core.launch(db, queued, job, [])
            running = dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM outcomes').fetchone()[0], 0)
            route = reviewer_routes.current_route(db)
        creates = [item for item in calls if item[0] == 'agent-create']
        self.assertEqual(len(creates), 2)
        self.assertEqual(creates[0][1]['provider'], 'claude')
        self.assertEqual(creates[0][1]['model'], 'claude-sonnet-5-5')
        self.assertEqual(creates[0][1]['thinkingOptionId'], 'high')
        self.assertNotRegex(creates[0][1]['idempotencyKey'], r'-r\d+$')
        self.assertEqual(creates[1][1]['provider'], 'codex')
        self.assertEqual(creates[1][1]['model'], 'gpt-6.1-sol')
        self.assertEqual(creates[1][1]['thinkingOptionId'], 'medium')
        self.assertIn('-r1', creates[1][1]['idempotencyKey'])
        self.assertEqual(creates[1][1]['cwd'], str(self.repo))
        self.assertEqual(queued['phase'], 'review')
        self.assertEqual(queued['attempt'], 2)
        self.assertEqual(queued['review_digest'], 'digest-under-review')
        self.assertEqual(running['phase'], 'review')
        self.assertEqual(running['attempt'], 2)
        self.assertEqual(running['model'], 'grok/grok-4.7')
        self.assertEqual(running['review_model'], 'codex/gpt-6.1-sol')
        self.assertEqual(running['state'], 'running')
        self.assertEqual(route['state'], 'fallback')
        self.assertTrue((self.repo/'.paseo-result.json').is_file())
        self.assertFalse((self.repo/'.paseo-review.json').exists())

    def test_old_policy_does_not_substitute_on_session_limit(self):
        model_limits.LIMITS_FILE = ROOT / '.maintenance-model-limits.json'
        self.catalog()
        with core.database() as db, patch.object(core, 'bridge', side_effect=RuntimeError("You've hit your session limit")):
            task = self.insert(db, state='queued', agent_id=None, review_model='codex/gpt-6.1-sol')
            job = dict(db.execute("SELECT * FROM jobs WHERE id='job'").fetchone())
            with self.assertRaises(core.LaunchUncertain):
                core.launch(db, task, job, [])
            row = dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone())
            self.assertIsNone(reviewer_routes.current_route(db))
        self.assertEqual(row['state'], 'launching')
        self.assertEqual(row['phase'], 'review')
        self.assertEqual(row['attempt'], 2)
        self.assertIsNotNone(row['launch_request'])
        self.assertNotIn('reviewer_substituted', row['error'])

    def test_plan_reviewer_route_cannot_force_fallback_without_quota_proof(self):
        self.catalog(sonnet_fraction=0.5, sol_fraction=0.5)
        spec = json.loads(self.spec)
        spec['reviewer_route'] = {'state': 'fallback', 'active_model': 'codex/gpt-6.1-sol', 'blocked_at': self.clock}
        self.spec = json.dumps(spec)
        with core.database() as db, patch.object(core, 'bridge', side_effect=AssertionError('model poll')):
            task = self.insert(db, state='queued', agent_id=None, review_model=None)
            result = core.select(db, task, [])
            self.assertIsNone(reviewer_routes.current_route(db))
        self.assertEqual(result['selected']['key'], 'claude/claude-sonnet-5-5')
        self.assertEqual(result['selected']['thinking_option_id'], 'high')
        self.assertEqual(result['selected']['provider'], 'claude')

    def test_new_review_returns_to_sonnet_while_substitute_finishes(self):
        self.clock = time.time() - 40
        with core.database() as db:
            running = self.insert(db, state='running', agent_id='rev-sonnet')
            reviewer_routes.note_session_quota(db, running, 'You have hit your session limit')
            self.clock = time.time()
            self.catalog(sonnet_fraction=0.4, sol_fraction=0.5)
            db.execute("""UPDATE tasks SET state='running', agent_id='rev-sol', review_model='codex/gpt-6.1-sol'
                          WHERE id='task'""")
            db.execute('''INSERT INTO tasks(id,job_id,task_key,spec,state,phase,attempt,model,review_model,agent_id,
                          cwd,workspace_id,review_digest,result,error,updated)
                          VALUES('next','job','second',?,'queued','review',2,'grok/grok-4.7',NULL,NULL,?,
                                 'workspace-1','digest-under-review','{"implementation":{"status":"completed"}}',NULL,?)''',
                       (self.spec, str(self.repo), self.clock))
            db.commit()
            queued = dict(db.execute("SELECT * FROM tasks WHERE id='next'").fetchone())
            active = dict(db.execute("SELECT * FROM tasks WHERE id='task'").fetchone())
            with patch.object(core, 'bridge', side_effect=AssertionError('model poll')):
                nxt = core.select(db, queued, [])
                held = core.select(db, active, [])
            route = reviewer_routes.current_route(db)
            unchanged = dict(db.execute(
                "SELECT agent_id,review_model,state,attempt,phase FROM tasks WHERE id='task'").fetchone())
        self.assertEqual(nxt['selected']['key'], 'claude/claude-sonnet-5-5')
        self.assertEqual(nxt['selected']['thinking_option_id'], 'high')
        self.assertEqual(held['selected']['key'], 'codex/gpt-6.1-sol')
        self.assertEqual(held['selected']['thinking_option_id'], 'medium')
        self.assertEqual(route['state'], 'fallback')
        self.assertEqual(route['active_model'], 'codex/gpt-6.1-sol')
        self.assertEqual(unchanged['agent_id'], 'rev-sol')
        self.assertEqual(unchanged['review_model'], 'codex/gpt-6.1-sol')
        self.assertEqual(unchanged['state'], 'running')
        self.assertEqual(unchanged['attempt'], 2)
        self.assertEqual(unchanged['phase'], 'review')
