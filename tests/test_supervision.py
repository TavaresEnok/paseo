import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import orchestrator.model_limits as model_limits
from orchestrator import core, supervision
from orchestrator.supervisor import prepare

ROOT = Path(__file__).resolve().parents[1]
model_limits.LIMITS_FILE = ROOT / '.maintenance-model-limits.json'
NEW_LIMITS = ROOT / '.new-role-model-limits.json'


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dev = self.root/'workspace'; self.dev.mkdir()
        self.state = self.root/'state'; self.state.mkdir()
        self.time = 1800000000
        self.settings = {'enabled': True, 'primary_model': 'claude/claude-opus-5-5',
                         'primary_thinking': 'medium', 'fallback_model': 'codex/gpt-6.1-sol',
                         'fallback_thinking': 'high', 'auto_return': True,
                         'quota_max_age_seconds': 300, 'retry_seconds': 60}
        self.agents = {'P': {'id': 'P', 'provider': 'claude', 'model': 'claude-opus-5-5',
                            'cwd': str(self.dev), 'workspaceId': 'W', 'status': 'idle',
                            'labels': {'flow.role': 'supervisor'}}}
        self.starts = []; self.sends = []; self.archived = []
        for p in [patch.object(core, 'STATE', self.state), patch.object(core, 'DEV', self.dev),
                  patch.object(core, 'now', side_effect=lambda: self.time),
                  patch.object(supervision, 'load_limits', return_value={'supervision': self.settings}),
                  patch.object(supervision, 'assess_resources', return_value={'allowed': True}),
                  patch.object(core, 'bridge', side_effect=self.native),
                  patch.object(supervision.supervisor, 'prepare', return_value={'provider':'codex','model':'gpt-6.1-sol','thinkingOptionId':'high'}),
                  patch.object(supervision.supervisor, 'start', side_effect=self.start)]:
            p.start(); self.addCleanup(p.stop)
        self.write_quota(0)
        with core.database() as db:
            for name in ['one', 'two']:
                db.execute('''INSERT INTO jobs(id,objective,repo,branch,plan,plan_hash,state,supervisor_id,created,updated)
                              VALUES(?,?,?,?,?,?,?,?,?,?)''',
                           (name, 'already approved request', str(self.dev), 'orchestration/'+name,
                            '{}', name, 'running', 'P', self.time, self.time))
            db.execute("INSERT INTO tasks(id,job_id,task_key,spec,state,attempt,updated) VALUES('task','one','original','{}','done',2,?)", (self.time,))

    def write_quota(self, fraction, observed=None, cost=True):
        model = {'provider': 'claude', 'id': 'claude-opus-5-5', 'authenticated': True,
                 'available': True, 'cost': {'verified': cost, 'additional_cost': 0},
                 'quota': {'source': 'native quota fixture', 'observed_at': self.time if observed is None else observed,
                           'windows': [{'remaining_fraction': fraction}]}}
        (self.state/'catalog.json').write_text(json.dumps({'models': [model]}))

    def native(self, action, **kwargs):
        if action == 'agents': return {'entries': [{'agent': a} for a in self.agents.values()]}
        if action == 'agent': return {'agent': self.agents[kwargs['agentId']]}
        if action == 'timeline': return {'entries': [{'item': {'type': 'user_message', 'text': 'Please preserve the original request'}}]}
        if action == 'send': self.sends.append(kwargs); return {}
        if action == 'archive': self.archived.append(kwargs['agentId']); self.agents.pop(kwargs['agentId'], None); return {}
        raise AssertionError(action)

    def start(self, repo, prompt, **kwargs):
        self.starts.append((repo, prompt, kwargs))
        aid = 'F'+str(len(self.starts))
        self.agents[aid] = {'id': aid, 'provider': 'codex', 'model': 'gpt-6.1-sol',
                            'status': 'idle', 'cwd': str(self.dev), 'workspaceId': 'W'}
        return {'agent_id': aid}

    def route(self):
        with core.database() as db:
            return dict(db.execute("SELECT * FROM supervisor_routes WHERE primary_id='P'").fetchone())

    def test_exhaustion_transfers_all_plans_once_without_touching_tasks(self):
        supervision.reconcile(); self.time += 31; supervision.reconcile()
        self.assertEqual(len(self.starts), 1)
        self.assertTrue(self.starts[0][2]['fallback'])
        self.assertEqual(self.starts[0][2]['workspace_id'], 'W')
        self.assertIn('original request', self.starts[0][1])
        with core.database() as db:
            self.assertEqual({r['supervisor_id'] for r in db.execute('SELECT supervisor_id FROM jobs')}, {'F1'})
            self.assertEqual(tuple(db.execute('SELECT state,attempt FROM tasks').fetchone()), ('done', 2))

    def test_fresh_replenishment_returns_to_original_opus_and_archives_fallback(self):
        supervision.reconcile(); self.time += 301; self.write_quota(.8)
        supervision.reconcile()
        self.assertEqual(self.route()['state'], 'primary')
        self.assertEqual(self.sends[0]['agentId'], 'P')
        self.assertIn('messageId', self.sends[0]['options'])
        self.assertEqual(self.archived, ['F1'])
        with core.database() as db:
            self.assertEqual({r['supervisor_id'] for r in db.execute('SELECT supervisor_id FROM jobs')}, {'P'})
            self.assertEqual(tuple(db.execute('SELECT state,attempt FROM tasks').fetchone()), ('done', 2))

    def test_does_not_return_on_unknown_stale_or_old_positive_quota(self):
        supervision.reconcile(); blocked = self.time; self.time += 301
        for fraction, observed in [(None, self.time), (.8, blocked-1), (.8, self.time-901), (0, self.time)]:
            self.write_quota(fraction, observed); supervision.reconcile()
            self.assertEqual(self.route()['state'], 'fallback')
        self.assertEqual(self.sends, [])

    def test_unknown_quota_is_not_exhaustion(self):
        self.write_quota(None); supervision.reconcile()
        self.assertEqual(self.starts, [])

    def test_manager_finishes_current_turn_before_return(self):
        supervision.reconcile(); self.time += 301; self.write_quota(.8)
        self.agents['F1']['status'] = 'running'; supervision.reconcile()
        self.assertEqual(self.sends, [])
        self.agents['F1']['status'] = 'idle'; supervision.reconcile()
        self.assertEqual(self.route()['state'], 'primary')

    def test_paused_plans_are_never_resumed(self):
        with core.database() as db: db.execute("UPDATE jobs SET state='paused'")
        supervision.reconcile()
        self.assertEqual(self.starts, [])
        with core.database() as db: self.assertEqual({r['state'] for r in db.execute('SELECT state FROM jobs')}, {'paused'})

    def test_ordinary_auth_failure_does_not_trigger_quota_transfer(self):
        self.write_quota(None); self.agents['P']['lastError'] = 'Authentication required'
        supervision.reconcile(); self.assertEqual(self.starts, [])
        self.agents['P']['lastError'] = 'rate_limit_error: usage limit reached'
        supervision.reconcile(); self.assertEqual(len(self.starts), 1)

    def test_native_error_item_can_detect_a_quota_error(self):
        self.write_quota(None); self.agents['P']['attentionReason'] = 'error'
        native = self.native
        def with_error(action, **kwargs):
            if action == 'timeline':return {'entries': [{'timestamp': datetime.datetime.fromtimestamp(self.time, datetime.timezone.utc).isoformat(),
                                                        'item': {'type': 'error', 'message': "You've hit your limit"}}]}
            return native(action, **kwargs)
        with patch.object(core, 'bridge', side_effect=with_error):supervision.reconcile()
        self.assertEqual(len(self.starts), 1)

    def test_error_before_first_controller_discovery_is_not_lost(self):
        self.write_quota(None);self.agents['P']['attentionReason']='error'
        native=self.native
        def with_error(action,**kwargs):
            if action=='timeline':return {'entries':[{'timestamp':datetime.datetime.fromtimestamp(self.time-20,datetime.timezone.utc).isoformat(),
                                                     'item':{'type':'error','message':"You've hit your limit"}}]}
            return native(action,**kwargs)
        with patch.object(core,'bridge',side_effect=with_error):supervision.reconcile()
        self.assertEqual(self.route()['state'],'fallback')

    def test_uncertain_create_retries_exact_request_after_restart(self):
        with patch.object(supervision.supervisor, 'start', side_effect=TimeoutError('receipt pending')) as start:
            supervision.reconcile(); first = start.call_args.kwargs['idempotency_key']
        self.assertEqual(self.route()['state'], 'switching_to_fallback')
        self.time += 61; supervision.reconcile()
        self.assertEqual(self.starts[0][2]['idempotency_key'], first)
        self.assertEqual(self.route()['state'], 'fallback')

    def test_uncertain_return_reuses_message_id_without_reassigning_early(self):
        supervision.reconcile(); self.time += 301; self.write_quota(.8)
        native = self.native; attempts = []
        def uncertain(action, **kwargs):
            if action == 'send': attempts.append(kwargs); raise TimeoutError('send acknowledgment lost')
            return native(action, **kwargs)
        with patch.object(core, 'bridge', side_effect=uncertain):supervision.reconcile()
        self.assertEqual(self.route()['active_id'], 'F1')
        self.time += 61; self.write_quota(.8); supervision.reconcile()
        self.assertEqual(self.sends[0]['options']['messageId'], attempts[0]['options']['messageId'])
        self.assertEqual(self.route()['active_id'], 'P')

    def test_second_exhaustion_uses_a_new_generation(self):
        supervision.reconcile(); key = self.starts[0][2]['idempotency_key']
        self.time += 301; self.write_quota(.8); supervision.reconcile()
        self.time += 301; self.write_quota(0); supervision.reconcile()
        self.assertEqual(self.route()['generation'], 2)
        self.assertNotEqual(key, self.starts[1][2]['idempotency_key'])

    def test_standalone_manager_can_transfer_before_submitting_a_plan(self):
        with core.database() as db:
            db.execute('DELETE FROM tasks'); db.execute('DELETE FROM jobs')
        supervision.reconcile()
        self.assertEqual(self.route()['state'], 'fallback')

    def test_if_both_are_exhausted_opus_resumes_when_only_its_quota_returns(self):
        with patch.object(supervision.supervisor, 'prepare', side_effect=RuntimeError('Sol quota exhausted')):
            supervision.reconcile()
            self.assertEqual(self.route()['state'], 'fallback_wait')
            self.assertEqual(self.starts, [])
            self.time += 301; self.write_quota(.8); supervision.reconcile()
        self.assertEqual(self.route()['state'], 'primary')
        self.assertEqual(self.sends[0]['agentId'], 'P')

    def test_busy_primary_is_not_interrupted_on_exhaustion(self):
        self.agents['P']['status']='running'; supervision.reconcile()
        self.assertEqual(self.starts, [])
        self.agents['P']['status']='idle'; supervision.reconcile()
        self.assertEqual(self.route()['state'], 'fallback')

    def test_standalone_project_manager_without_labels_is_covered(self):
        project=self.dev/'project';project.mkdir()
        self.agents['P'].update(cwd=str(project),labels={})
        with core.database() as db:
            db.execute('DELETE FROM tasks');db.execute('DELETE FROM jobs')
        supervision.reconcile()
        self.assertEqual(self.route()['state'],'fallback')

    def test_all_quota_windows_must_recover_and_cost_must_be_verified(self):
        supervision.reconcile();self.time+=301;self.write_quota(.8,cost=False)
        supervision.reconcile();self.assertEqual(self.route()['state'],'fallback')
        self.write_quota(.8)
        p=self.state/'catalog.json';d=json.loads(p.read_text())
        d['models'][0]['quota']['windows'].append({'remaining_fraction':0})
        p.write_text(json.dumps(d));supervision.reconcile()
        self.assertEqual(self.route()['state'],'fallback')

    def _sol_manager(self, agent_id='M', thinking='high', labels=None):
        return {'id': agent_id, 'provider': 'codex', 'model': 'gpt-6.1-sol', 'cwd': str(self.dev),
                'workspaceId': 'W', 'status': 'idle', 'thinkingOptionId': thinking,
                'labels': {'flow.role': 'supervisor', 'flow.supervisor.role': 'primary',
                           'flow.supervisor.thinking': thinking} if labels is None else labels}

    def test_sol_primary_is_not_confused_with_reviewers_or_old_routes(self):
        limits = json.loads(NEW_LIMITS.read_text())
        self.agents = {
            'P': {'id': 'P', 'provider': 'claude', 'model': 'claude-opus-5-5', 'cwd': str(self.dev),
                  'workspaceId': 'W', 'status': 'idle', 'thinkingOptionId': 'medium',
                  'labels': {'flow.role': 'supervisor'}},
            'M': self._sol_manager(),
            'Rmed': self._sol_manager('Rmed', 'medium', {'flow.phase': 'review', 'flow.role': 'reviewer'}),
            'Rlow': self._sol_manager('Rlow', 'low', {'flow.phase': 'review', 'flow.role': 'reviewer'}),
            'Smed': self._sol_manager('Smed', 'medium'),
            'Work': self._sol_manager('Work', 'high', {'flow.phase': 'implement', 'flow.task': 'task-1', 'flow.role': 'worker'}),
            'Bare': self._sol_manager('Bare', 'high', {}),
            'OldFb': self._sol_manager('OldFb', 'high', {'flow.role': 'supervisor', 'flow.supervisor.role': 'fallback',
                                                         'flow.supervisor.request': 'supervisor-route-P-1-fallback'}),
            'OldFb2': self._sol_manager('OldFb2', 'high'),
        }
        (self.state/'catalog.json').write_text(json.dumps({'models': [{
            'provider': 'codex', 'id': 'gpt-6.1-sol', 'authenticated': True, 'available': True,
            'cost': {'verified': True, 'additional_cost': 0},
            'quota': {'source': 'fixture', 'observed_at': self.time, 'windows': [{'remaining_fraction': 0.5}]}}]}))
        with patch.object(supervision, 'load_limits', return_value=limits):
            with core.database() as db:
                supervision.initialize(db)
                db.execute('''INSERT INTO supervisor_routes(primary_id,active_id,state,fallback_id,updated,next_check)
                              VALUES('P','P','primary','OldFb2',?,0)''', (self.time,))
                db.commit()
            supervision.reconcile()
            with core.database() as db:
                routes = {row['primary_id']: dict(row) for row in db.execute('SELECT * FROM supervisor_routes')}
                owners = {row['supervisor_id'] for row in db.execute('SELECT supervisor_id FROM jobs')}
        self.assertEqual(set(routes), {'P', 'M', 'Bare'})
        self.assertEqual(routes['M']['state'], 'primary')
        self.assertEqual(routes['M']['active_id'], 'M')
        self.assertEqual(routes['Bare']['state'], 'primary')
        self.assertEqual(routes['Bare']['active_id'], 'Bare')
        self.assertEqual(routes['P']['state'], 'primary')
        self.assertEqual(owners, {'P'})
        self.assertEqual(self.starts, [])
        self.assertEqual(self.sends, [])

    def test_unlabeled_sol_high_in_a_worktree_is_not_a_manager(self):
        limits = json.loads(NEW_LIMITS.read_text())
        work = self.root/'worktrees'
        job = work/'job'
        job.mkdir(parents=True)
        self.agents = {'W': self._sol_manager('W', 'high', {})}
        self.agents['W']['cwd'] = str(job)
        with patch.object(core, 'WORKTREES', work), patch.object(supervision, 'load_limits', return_value=limits):
            supervision.reconcile()
            with core.database() as db:
                routes = list(db.execute('SELECT primary_id FROM supervisor_routes'))
        self.assertEqual(routes, [])

    def test_ambiguous_shared_effort_requires_an_explicit_supervisor_role(self):
        limits = json.loads(NEW_LIMITS.read_text())
        limits['review']['fallback_thinking_option'] = 'high'
        bare = self._sol_manager('Bare', 'high', {})
        labeled = self._sol_manager('Lab', 'high', {'flow.role': 'supervisor'})
        medium = self._sol_manager('Med', 'medium', {})
        with patch.object(supervision, 'load_limits', return_value=limits):
            with core.database() as db:
                supervision.initialize(db)
                settings = limits['supervision']
                self.assertFalse(supervision.discoverable_manager(bare, settings, limits, db))
                self.assertTrue(supervision.discoverable_manager(labeled, settings, limits, db))
                self.assertFalse(supervision.discoverable_manager(medium, settings, limits, db))

    def test_explicit_migration_preserves_paused_canceled_context_and_makes_no_calls(self):
        limits = json.loads(NEW_LIMITS.read_text())
        manager = self._sol_manager()
        with patch.object(supervision, 'load_limits', return_value=limits):
            with core.database() as db:
                supervision.initialize(db)
                db.execute('''INSERT INTO supervisor_routes(primary_id,active_id,state,fallback_id,generation,updated,next_check)
                              VALUES('P','F','fallback','F',3,?,0)''', (self.time,))
                db.execute("UPDATE jobs SET supervisor_id='F' WHERE id='one'")
                db.execute("UPDATE jobs SET state='paused' WHERE id='two'")
                db.execute('''INSERT INTO jobs(id,objective,repo,branch,plan,plan_hash,state,supervisor_id,created,updated)
                              VALUES('three','canceled request',?, 'orchestration/three','{}','three','canceled','P',?,?)''',
                           (str(self.dev), self.time, self.time))
                supervision.migrate_supervisor_route(db, 'P', 'M', manager)
                again = supervision.migrate_supervisor_route(db, 'P', 'M', manager)
                jobs = {row['id']: dict(row) for row in db.execute('SELECT id,state,supervisor_id FROM jobs')}
                old = dict(db.execute("SELECT * FROM supervisor_routes WHERE primary_id='P'").fetchone())
                new = dict(db.execute("SELECT * FROM supervisor_routes WHERE primary_id='M'").fetchone())
                task = db.execute('SELECT state,attempt FROM tasks').fetchone()
                kinds = [row['kind'] for row in db.execute("SELECT kind FROM events WHERE kind='supervisor_route_migrated'")]
                with self.assertRaises(RuntimeError):
                    supervision.migrate_supervisor_route(db, 'P', 'R', self._sol_manager('R', 'medium', {'flow.phase': 'review', 'flow.role': 'reviewer'}))
        self.assertEqual(jobs['one']['state'], 'running')
        self.assertEqual(jobs['one']['supervisor_id'], 'M')
        self.assertEqual(jobs['two']['state'], 'paused')
        self.assertEqual(jobs['two']['supervisor_id'], 'P')
        self.assertEqual(jobs['three']['state'], 'canceled')
        self.assertEqual(jobs['three']['supervisor_id'], 'P')
        self.assertEqual(old['state'], 'superseded')
        self.assertEqual(new['state'], 'primary')
        self.assertEqual(new['active_id'], 'M')
        self.assertEqual(tuple(task), ('done', 2))
        self.assertTrue(again['migrated'])
        self.assertEqual(kinds, ['supervisor_route_migrated', 'supervisor_route_migrated'])
        self.assertEqual(self.starts, [])
        self.assertEqual(self.sends, [])

    def test_handoff_text_comes_from_settings(self):
        limits = json.loads(NEW_LIMITS.read_text())
        self.agents = {'P': self._sol_manager('P')}
        (self.state/'catalog.json').write_text(json.dumps({'models': [{
            'provider': 'codex', 'id': 'gpt-6.1-sol', 'authenticated': True, 'available': True,
            'cost': {'verified': True, 'additional_cost': 0, 'kind': 'subscription', 'source': 'fixture'},
            'quota': {'source': 'fixture', 'observed_at': self.time, 'windows': [{'remaining_fraction': 0}]}}]}))
        with patch.object(supervision, 'load_limits', return_value=limits):
            supervision.reconcile()
        prompt = self.starts[0][1]
        self.assertIn('codex/gpt-6.1-sol (high)', prompt)
        self.assertIn('claude/claude-opus-5-5 (medium)', prompt)
        self.assertIn('original request', prompt)
        self.assertNotIn('Opus 5.5 Médio é o gerente principal', prompt)
        self.assertNotIn('Sol Baixo', prompt)
        self.assertNotIn('GPT-6.1 Sol', prompt)


class SupervisorPromptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dev = Path(self.tmp.name).resolve()/'workspace'
        self.dev.mkdir()
        self.state = Path(self.tmp.name)/'state'
        self.state.mkdir()
        self.previous = model_limits.LIMITS_FILE
        for item in (patch.object(core, 'STATE', self.state), patch.object(core, 'DEV', self.dev),
                     patch.object(core, 'autonomy_policy', return_value={})):
            item.start(); self.addCleanup(item.stop)

    def tearDown(self):
        model_limits.LIMITS_FILE = self.previous

    def catalog(self, *models):
        stamped = []
        for provider, model_id in models:
            stamped.append({'provider': provider, 'id': model_id, 'available': True, 'authenticated': True,
                            'observed_at': time.time(), 'source': 'fixture',
                            'cost': {'kind': 'subscription', 'verified': True, 'additional_cost': 0, 'source': 'fixture'},
                            'safe_thinking_options': ['low', 'medium', 'high']})
        (self.state/'catalog.json').write_text(json.dumps({'models': stamped}))

    def test_titles_follow_old_and_new_policy(self):
        model_limits.LIMITS_FILE = ROOT/'.maintenance-model-limits.json'
        self.catalog(('claude', 'claude-opus-5-5'))
        old = prepare(str(self.dev), 'objetivo antigo')
        self.assertEqual(old['title'], 'Gerente principal — claude/claude-opus-5-5 medium')
        self.assertIn('Gerente principal: claude/claude-opus-5-5 (medium)', old['systemPrompt'])
        self.assertNotIn('Opus 5.5 Médio é o gerente principal', old['systemPrompt'])
        self.assertEqual(old['labels']['flow.supervisor.role'], 'primary')
        self.assertEqual(old['labels']['flow.supervisor.thinking'], 'medium')
        model_limits.LIMITS_FILE = NEW_LIMITS
        self.catalog(('codex', 'gpt-6.1-sol'), ('claude', 'claude-opus-5-5'))
        primary = prepare(str(self.dev), 'objetivo novo')
        fallback = prepare(str(self.dev), 'objetivo novo', fallback=True)
        self.assertEqual(primary['title'], 'Gerente principal — codex/gpt-6.1-sol high')
        self.assertEqual(primary['thinkingOptionId'], 'high')
        self.assertEqual(primary['labels']['flow.role'], 'supervisor')
        self.assertIn('Revisor principal: claude/claude-sonnet-5-5 (high)', primary['systemPrompt'])
        self.assertEqual(fallback['title'], 'Gerente substituto — claude/claude-opus-5-5 medium')
        self.assertEqual(fallback['model'], 'claude-opus-5-5')
        self.assertEqual(fallback['thinkingOptionId'], 'medium')
        self.assertEqual(fallback['labels']['flow.supervisor.role'], 'fallback')

    def test_manager_root_child_is_management_but_not_a_job_path(self):
        projects = Path(self.tmp.name).resolve()/'projetos'
        child = projects/'webchat'
        child.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(child)], check=True)
        model_limits.LIMITS_FILE = NEW_LIMITS
        self.catalog(('codex', 'gpt-6.1-sol'), ('claude', 'claude-opus-5-5'))
        plan = {
            'objective': 'não submeter job aqui',
            'repo': str(child),
            'tasks': [{
                'id': 'job1', 'objective': 'implementar', 'acceptance': ['ok'],
                'allowed_files': ['modulo.py'], 'tests': [['python3', '-m', 'unittest']],
                'timeout_seconds': 60,
            }],
        }
        limits = json.loads(NEW_LIMITS.read_text())
        bare = {'id': 'web', 'provider': 'codex', 'model': 'gpt-6.1-sol', 'cwd': str(child),
                'thinkingOptionId': 'high', 'labels': {}}
        reviewer = {'id': 'rev', 'provider': 'codex', 'model': 'gpt-6.1-sol', 'cwd': str(child),
                    'thinkingOptionId': 'medium', 'labels': {'flow.phase': 'review', 'flow.role': 'reviewer'}}
        with patch.object(core, 'MANAGER_ROOT', projects, create=True):
            with patch.object(core, 'autonomy_policy', return_value={}):
                with self.assertRaisesRegex(ValueError, 'clone de desenvolvimento'):
                    core.dev_path(child)
                with self.assertRaisesRegex(ValueError, 'não autorizado'):
                    core.manager_cwd(child)
                with self.assertRaisesRegex(ValueError, 'clone de desenvolvimento'):
                    core.validate_plan(plan)
            for policy in ({'unrestricted_tools': True}, {'manager_host_access': True}):
                with patch.object(core, 'autonomy_policy', return_value=policy):
                    self.assertEqual(core.manager_cwd(child), child.resolve())
                    with self.assertRaisesRegex(ValueError, 'clone de desenvolvimento'):
                        core.dev_path(child)
                    with self.assertRaisesRegex(ValueError, 'clone de desenvolvimento'):
                        core.validate_plan(plan)
                    options = prepare(str(child), 'gerir o webchat')
                    self.assertEqual(options['cwd'], str(child.resolve()))
                    self.assertEqual(options['title'], 'Gerente principal — codex/gpt-6.1-sol high')
                    with core.database() as db:
                        supervision.initialize(db)
                        self.assertTrue(supervision.discoverable_manager(bare, limits['supervision'], limits, db))
                        self.assertFalse(supervision.discoverable_manager(reviewer, limits['supervision'], limits, db))
        with patch.object(core, 'autonomy_policy', return_value={'unrestricted_tools': True, 'manager_host_access': True}):
            with self.assertRaisesRegex(ValueError, 'clone de desenvolvimento|Diretório de gerência não autorizado'):
                core.manager_cwd(child)

    def test_nexo_manager_host_cwd_admits_project_children_only(self):
        candidates = [ROOT/'nexo-port'/'native'/'isolated-provider.py', ROOT/'native'/'isolated-provider.py']
        path = next(item for item in candidates if item.is_file())
        spec = importlib.util.spec_from_file_location('nexo_isolated_provider', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = Path('/home/enok/Documentos/projetos')
        self.assertTrue(module.manager_host_cwd(root, root))
        self.assertTrue(module.manager_host_cwd(root/'webchat', root))
        self.assertTrue(module.manager_host_cwd(root/'webchat'/'src', root))
        self.assertFalse(module.manager_host_cwd(Path('/home/enok/srv_projetos/worktrees/job'), root))
        self.assertFalse(module.manager_host_cwd(Path('/tmp/other'), root))
        self.assertNotIn('is_relative_to', module.manager_host_cwd.__code__.co_names)

    def test_host_access_without_unrestricted_tools_runs_manager_and_rejects_workers(self):
        candidates = [ROOT/'nexo-port'/'native'/'isolated-provider.py', ROOT/'native'/'isolated-provider.py']
        path = next(item for item in candidates if item.is_file() and 'host_manager_session' in item.read_text())
        spec = importlib.util.spec_from_file_location('nexo_isolated_provider_main', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.ROOTS = [module.BASE/'workspace', module.BASE/'worktrees']
        self.assertNotIn(Path('/home/enok/Documentos/projetos'), module.ROOTS)
        policy = json.dumps({'manager_host_access': True, 'unrestricted_tools': False})
        autonomy = (module.BASE/'config'/'autonomy.json').resolve()
        webchat = Path('/home/enok/Documentos/projetos')/'webchat'
        original_read = module.Path.read_text
        original_is_dir = module.Path.is_dir
        def read_text(target, *args, **kwargs):
            if Path(target).resolve()==autonomy:
                return policy
            return original_read(target, *args, **kwargs)
        def is_dir(target):
            if str(target).startswith(str(module.RUNTIME)):
                return True
            return original_is_dir(target)
        class Stopped(Exception):
            pass
        def stop(*_args, **_kwargs):
            raise Stopped()
        def run_provider(provider, cwd):
            with patch.dict(os.environ, {'PASEO_AGENT_ID':'mgr','PASEO_AGENT_CWD':str(cwd)}), \
                 patch.object(sys, 'argv', ['wrapper', provider, '--version']), \
                 patch.object(module.os, 'execve', side_effect=stop) as execve, \
                 patch.object(module.os, 'execv', side_effect=stop) as execv, \
                 patch.object(module.os, 'chdir') as chdir, \
                 patch.object(module.Path, 'read_text', read_text), \
                 patch.object(module.Path, 'is_dir', is_dir), \
                 patch.object(module.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')):
                try:
                    module.main()
                except Stopped:
                    return execve, execv, chdir, None
                except SystemExit as exc:
                    return execve, execv, chdir, exc
            return execve, execv, chdir, None
        execve, execv, chdir, error = run_provider('codex', webchat)
        self.assertIsNone(error)
        execv.assert_not_called()
        execve.assert_called_once()
        chdir.assert_called_once_with(webchat.resolve())
        binary, argv, env = execve.call_args.args
        self.assertEqual(binary, str(module.NODE/'bin'/'codex'))
        self.assertNotIn('/usr/bin/docker', argv)
        self.assertEqual(env.get('PASEO_MANAGER_HOST_ACCESS'), '1')
        self.assertNotIn('seccomp', ' '.join(argv))
        _execve, _execv, _chdir, error = run_provider('grok', webchat)
        self.assertIsInstance(error, SystemExit)
        self.assertIn('outside approved development roots', str(error))
        _execve.assert_not_called()
        _execv.assert_not_called()
        worktree = module.BASE/'worktrees'/'job'
        execve, execv, chdir, error = run_provider('codex', worktree)
        self.assertIsNone(error)
        execve.assert_not_called()
        execv.assert_called_once()
        docker_args = execv.call_args.args[1]
        self.assertEqual(docker_args[0], '/usr/bin/docker')
        self.assertIn('seccomp=/home/enok/srv_projetos/config/seccomp-default.json', docker_args)
        self.assertIn('GOCACHE=', ' '.join(docker_args))

