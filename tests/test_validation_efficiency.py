import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from orchestrator import core, validation
from orchestrator.validation import RUNNER_IMAGE, inspect_local_image, proof_valid, reuse_decision, runner_stamp


class ValidationEfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'workspace' / 'repo'
        self.repo.mkdir(parents=True)
        self.state = self.root / 'state'
        self.worktrees = self.root / 'worktrees'
        self.worktrees.mkdir()
        self.image_fixture = patch.object(validation, 'inspect_local_image', return_value={
            'id': 'sha256:' + 'ab' * 32,
            'digests': ['sha256:' + 'cd' * 32],
        })
        self.patches = [
            patch.object(core, 'archive_worker'),
            patch.object(core, 'STATE', self.state),
            patch.object(core, 'DEV', self.root / 'workspace'),
            patch.object(core, 'WORKTREES', self.worktrees),
            patch.object(core, 'AUTONOMY_FILE', self.root / 'autonomy.json'),
            # Existing review, checkpoint and legacy cases need a verifiable runner.
            # This fixture stands in for local image inspect so those cases do not open a Docker socket.
            self.image_fixture,
        ]
        for item in self.patches:
            item.start()
        self.old_agent = os.environ.pop('PASEO_AGENT_ID', None)
        core.git(self.repo, 'init')
        core.git(self.repo, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        (self.repo / 'module.py').write_text('value = 1\n')
        core.git(self.repo, 'add', '.')
        core.git(self.repo, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'baseline')
        self.legacy = self._plan()
        self.optin = self._plan(policy=True)

    def tearDown(self):
        if self.old_agent is not None:
            os.environ['PASEO_AGENT_ID'] = self.old_agent
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def _plan(self, policy=False, checkpoint=False):
        tasks = [
            {'id': 'first', 'objective': 'Change module', 'acceptance': ['value is two'], 'allowed_files': ['module.py'],
             'tests': [['python3', '-m', 'unittest', 'test_first']], 'timeout_seconds': 60, 'max_attempts': 3},
            {'id': 'second', 'objective': 'Read module', 'acceptance': ['verified'], 'allowed_files': ['other.py'],
             'tests': [['python3', '-m', 'unittest', 'test_second']], 'depends_on': ['first']},
        ]
        if checkpoint:
            tasks[0]['validation_checkpoint'] = True
        plan = {'objective': 'Synthetic validation plan', 'repo': str(self.repo), 'tasks': tasks}
        if policy:
            plan['validation_policy'] = {
                'mode': 'proportional_v1',
                'final_tests': [['python3', '-m', 'unittest', 'test_first'], ['python3', '-m', 'unittest', 'tests.test_core']],
            }
        return plan

    def _submit(self, plan):
        result = core.submit(plan, supervisor_id='supervisor-fixture')
        core.approve(result['job_id'], reason='test authorization')
        with core.database() as db:
            job = dict(db.execute('SELECT * FROM jobs WHERE id=?', (result['job_id'],)).fetchone())
            task = dict(db.execute('SELECT * FROM tasks WHERE job_id=? ORDER BY rowid', (job['id'],)).fetchone())
        return job, task

    def _bind_worker(self, job, task):
        base = core.git(self.repo, 'rev-parse', 'HEAD')
        with core.database() as db:
            db.execute('UPDATE tasks SET workspace_id=?,cwd=?,branch=?,base_commit=? WHERE id=?',
                       ('workspace-fixture', str(self.repo), job['branch'], base, task['id']))
            return dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())

    def _events(self, db, job_id, kind=None):
        query = 'SELECT kind,data FROM events WHERE job_id=?'
        args = [job_id]
        if kind:
            query += ' AND kind=?'
            args.append(kind)
        query += ' ORDER BY seq'
        return [(row['kind'], core.decode(row['data'])) for row in db.execute(query, args)]

    def test_legacy_plan_unchanged_and_invalid_policy_rejected(self):
        core.validate_plan(self.legacy)
        job, _task = self._submit(self.legacy)
        with core.database() as db:
            stored = db.execute('SELECT plan FROM jobs WHERE id=?', (job['id'],)).fetchone()[0]
            before = stored
            job_columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            task_columns = {row['name'] for row in db.execute('PRAGMA table_info(tasks)')}
        self.assertNotIn('validation_policy', json.loads(stored))
        core.database()
        with core.database() as db:
            self.assertEqual(db.execute('SELECT plan FROM jobs WHERE id=?', (job['id'],)).fetchone()[0], before)
        self.assertNotIn('validation_proof', job_columns | task_columns)
        valid = copy.deepcopy(self.optin)
        core.validate_plan(valid)
        rejected = [
            {'mode': 'proportional_v1', 'final_tests': []},
            {'mode': 'proportional_v2', 'final_tests': [['python3', '-m', 'unittest']]},
            {'mode': 'proportional_v1', 'final_tests': 'python3 -m unittest'},
            {'mode': 'proportional_v1', 'final_tests': [['python3', '-m', 'unittest']], 'enabled': True},
            {'final_tests': [['python3', '-m', 'unittest']]},
            [],
        ]
        for policy in rejected:
            invalid = copy.deepcopy(self.legacy)
            invalid['validation_policy'] = policy
            with self.assertRaises(ValueError):
                core.validate_plan(invalid)
        checkpoint = copy.deepcopy(self.optin)
        checkpoint['tasks'][0]['validation_checkpoint'] = 'yes'
        with self.assertRaisesRegex(ValueError, 'validation_checkpoint'):
            core.validate_plan(checkpoint)
        with core.database() as db:
            self.assertEqual(db.execute('SELECT plan FROM jobs WHERE id=?', (job['id'],)).fetchone()[0], before)

    def test_legacy_paths_still_accumulate_and_repeat_review_checks(self):
        job, task = self._submit(self.legacy)
        task = self._bind_worker(job, task)
        digest = core.worktree_digest(self.repo)
        (self.repo / '.paseo-review.json').write_text('{"decision":"pass","issues":[],"summary":"ok"}')
        with core.database() as db:
            other = db.execute("SELECT * FROM tasks WHERE task_key='second'").fetchone()
            spec = core.decode(other['spec'])
            spec['tests'] = [['python3', '-m', 'unittest', 'test_second']]
            db.execute("UPDATE tasks SET state='done',spec=? WHERE id=?", (core.encoded(spec), other['id']))
            db.execute("UPDATE tasks SET state='running',phase='review',review_digest=?,result='{}',branch=? WHERE id=?",
                       (digest, job['branch'], task['id']))
            task = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            with patch.object(core, 'test_commands', return_value=[{'exit_code': 0, 'stdout': 'pass'}]) as tests:
                core.finish_task(db, task, job)
            self.assertGreaterEqual(tests.call_count, 2)
            self.assertEqual(tests.call_args_list[0].args[1], [['python3', '-m', 'unittest', 'test_first']])
            self.assertEqual(tests.call_args_list[1].args[1], [
                ['python3', '-m', 'unittest', 'test_first'],
                ['python3', '-m', 'unittest', 'test_second'],
            ])
            self.assertNotIn('validation_reused', [kind for kind, _data in self._events(db, job['id'])])

    def test_opt_in_integration_runs_only_the_task_checks(self):
        job, task = self._submit(self.optin)
        task = self._bind_worker(job, task)
        head = core.git(self.repo, 'rev-parse', 'HEAD')
        with core.database() as db:
            other = db.execute("SELECT * FROM tasks WHERE task_key='second'").fetchone()
            spec = core.decode(other['spec'])
            spec['tests'] = [['python3', '-m', 'unittest', 'test_second']]
            db.execute("UPDATE tasks SET state='done',spec=? WHERE id=?", (core.encoded(spec), other['id']))
            db.execute("UPDATE tasks SET state='integrating',phase='integrate',commit_sha=?,result='{}' WHERE id=?", (head, task['id']))
            task = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            with patch.object(core, 'test_commands', return_value=[{'command': ['python3', '-m', 'unittest', 'test_first'], 'exit_code': 0}]) as tests:
                core.integrate_task(db, task, job)
            self.assertEqual(tests.call_args.args[1], [['python3', '-m', 'unittest', 'test_first']])
            row = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            result = core.decode(row['result'])
            self.assertEqual(result['validation_integration']['counts'], {'executed': 1, 'reused': 0})
            self.assertEqual(result['validation_integration']['commands'], [['python3', '-m', 'unittest', 'test_first']])
            self.assertEqual(db.execute('SELECT state FROM tasks WHERE id=?', (other['id'],)).fetchone()[0], 'done')

    def test_checkpoint_runs_final_suite_on_combined_head(self):
        plan = self._plan(policy=True, checkpoint=True)
        job, task = self._submit(plan)
        task = self._bind_worker(job, task)
        head = core.git(self.repo, 'rev-parse', 'HEAD')
        calls = []

        def fake(_cwd, commands, timeout=120):
            calls.append(commands)
            return [{'command': command, 'exit_code': 0} for command in commands]

        with core.database() as db:
            other = db.execute("SELECT id FROM tasks WHERE task_key='second'").fetchone()
            db.execute("UPDATE tasks SET state='done' WHERE id=?", (other['id'],))
            db.execute("UPDATE tasks SET state='integrating',phase='integrate',commit_sha=?,result='{}' WHERE id=?", (head, task['id']))
            task = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            with patch.object(core, 'test_commands', side_effect=fake):
                core.integrate_task(db, task, job)
            self.assertEqual(calls, [[
                ['python3', '-m', 'unittest', 'test_first'],
                ['python3', '-m', 'unittest', 'tests.test_core'],
            ]])
            proof = self._events(db, job['id'], 'final_validation')[-1][1]
            self.assertTrue(proof['passed'])
            self.assertEqual(proof['head'], head)
            self.assertEqual(proof['counts']['executed'], 2)
            self.assertNotIn('HOME', json.dumps(proof))
            with patch.object(core, 'bridge', return_value={}), patch.object(core, 'test_commands', side_effect=fake):
                core.tick()
            self.assertEqual(len(calls), 1)
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?', (job['id'],)).fetchone()[0], 'done')
            reused = self._events(db, job['id'], 'final_validation')[-1][1]
            self.assertEqual(reused['action'], 'reused')
            self.assertEqual(reused['counts'], {'executed': 0, 'reused': 2})

    def test_controller_reuses_valid_evidence_after_immutable_review(self):
        job, task = self._submit(self.optin)
        task = self._bind_worker(job, task)
        (self.repo / '.paseo-result.json').write_text(json.dumps({
            'status': 'completed',
            'tests': [{'command': ['fake'], 'exit_code': 0, 'stdout': 'model said pass'}],
        }))
        calls = []

        def fake(_cwd, commands, timeout=120):
            calls.append(list(commands))
            return [{'command': command, 'exit_code': 0, 'stdout': 'x' * 8000, 'stderr': ''} for command in commands]

        with core.database() as db, patch.object(core, 'test_commands', side_effect=fake):
            core.finish_task(db, task, job)
            task = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            result = core.decode(task['result'])
            self.assertEqual(calls, [[['python3', '-m', 'unittest', 'test_first']]])
            self.assertEqual(result['validation']['checks'][0]['command'], ['python3', '-m', 'unittest', 'test_first'])
            self.assertNotIn('stdout', result['validation']['checks'][0])
            self.assertEqual(result['validation']['counts'], {'executed': 1, 'reused': 0})
            self.assertEqual(result['validation']['digest'], task['review_digest'])
            (self.repo / '.paseo-review.json').write_text('{"decision":"pass","issues":[],"summary":"ok"}')
            db.execute("UPDATE tasks SET state='running',phase='review',agent_id='rev' WHERE id=?", (task['id'],))
            task = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            calls.clear()
            core.finish_task(db, task, job)
            reused = self._events(db, job['id'], 'validation_reused')
            self.assertEqual(len(reused), 1)
            self.assertEqual(reused[0][1]['counts'], {'executed': 0, 'reused': 1})
            self.assertEqual(calls, [[['python3', '-m', 'unittest', 'test_first']]])
            self.assertEqual(db.execute('SELECT state FROM tasks WHERE id=?', (task['id'],)).fetchone()[0], 'done')

    def test_invalid_evidence_runs_checks_again(self):
        cases = []
        stamp = runner_stamp(self.repo, core.NODE)
        self.assertIsNotNone(stamp)

        def prepare(evidence, tests=None, stamp_value=stamp):
            job, task = self._submit(self.optin)
            task = self._bind_worker(job, task)
            current = core.worktree_digest(self.repo)
            if tests is not None:
                spec = core.decode(task['spec'])
                spec['tests'] = tests
                encoded_spec = core.encoded(spec)
            else:
                encoded_spec = task['spec']
            (self.repo / '.paseo-review.json').write_text('{"decision":"pass","issues":[],"summary":"ok"}')
            with core.database() as db:
                db.execute("UPDATE tasks SET state='running',phase='review',review_digest=?,result=?,spec=?,branch=? WHERE id=?",
                           (current, core.encoded({'validation': evidence} if evidence is not None else {}), encoded_spec, job['branch'], task['id']))
                task = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            return job, task

        base_evidence = {
            'passed': True,
            'digest': core.worktree_digest(self.repo),
            'commands': [['python3', '-m', 'unittest', 'test_first']],
            'runner': stamp,
            'checks': [{'command': ['python3', '-m', 'unittest', 'test_first'], 'exit_code': 0, 'status': 'passed'}],
        }
        variants = [
            ('ausente', None, None, None),
            ('falha', {**base_evidence, 'passed': False, 'checks': [{**base_evidence['checks'][0], 'exit_code': 1}]}, None, None),
            ('digest', {**base_evidence, 'digest': 'stale'}, None, None),
            ('comandos', base_evidence, [['python3', '-m', 'unittest', 'test_other']], None),
            ('runner', base_evidence, None, {'id': 'other-runner', 'image': stamp['image']}),
            ('ambiente', base_evidence, None, None),
        ]
        for name, evidence, tests, patched in variants:
            job, task = prepare(evidence, tests)
            calls = []

            def fake(_cwd, commands, timeout=120, bucket=calls):
                bucket.append(commands)
                return [{'command': command, 'exit_code': 1, 'stderr': name + ' regression'} for command in commands]

            with core.database() as db:
                if name == 'ambiente':
                    runner_patch = patch.object(core, 'runner_stamp', return_value=None)
                elif name == 'runner':
                    runner_patch = patch.object(core, 'runner_stamp', return_value=patched)
                else:
                    runner_patch = None
                patches = [patch.object(core, 'test_commands', side_effect=fake)]
                if runner_patch:
                    patches.append(runner_patch)
                for item in patches:
                    item.start()
                try:
                    core.finish_task(db, task, job)
                finally:
                    for item in reversed(patches):
                        item.stop()
                row = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
                kinds = [kind for kind, _data in self._events(db, job['id'])]
            self.assertTrue(calls, name)
            self.assertIn('Regressão após revisão', row['error'], name)
            self.assertIn(name + ' regression', row['error'], name)
            self.assertNotIn('validation_reused', kinds, name)
            executed = [data for kind, data in self._events(db, job['id'], 'tests_executed')]
            self.assertEqual(executed[-1]['counts']['executed'], 1, name)
            self.assertEqual(executed[-1]['counts']['reused'], 0, name)
            cases.append(name)
        self.assertEqual(cases, ['ausente', 'falha', 'digest', 'comandos', 'runner', 'ambiente'])

    def test_reviewer_edits_and_mutating_checks_stay_blocked(self):
        job, task = self._submit(self.optin)
        task = self._bind_worker(job, task)
        (self.repo / '.paseo-review.json').write_text('{"decision":"pass","issues":[],"summary":"edited"}')
        with core.database() as db:
            db.execute("UPDATE tasks SET state='running',phase='review',review_digest='not-the-tree',result='{}',branch=? WHERE id=?",
                       (job['branch'], task['id']))
            task = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            with patch.object(core, 'test_commands') as tests:
                core.finish_task(db, task, job)
                tests.assert_not_called()
            self.assertIn('Revisor alterou o código', db.execute('SELECT error FROM tasks WHERE id=?', (task['id'],)).fetchone()[0])

        job, task = self._submit(self.optin)
        task = self._bind_worker(job, task)
        digest = core.worktree_digest(self.repo)
        (self.repo / '.paseo-review.json').write_text('{"decision":"pass","issues":[],"summary":"ok"}')

        def mutate(cwd, commands, timeout=120):
            (Path(cwd) / 'module.py').write_text('value = 9\n')
            return [{'command': command, 'exit_code': 0} for command in commands]

        with core.database() as db:
            db.execute("UPDATE tasks SET state='running',phase='review',review_digest=?,result='{}',branch=? WHERE id=?",
                       (digest, job['branch'], task['id']))
            task = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            with patch.object(core, 'test_commands', side_effect=mutate):
                core.finish_task(db, task, job)
            self.assertIn('modificaram o código', db.execute('SELECT error FROM tasks WHERE id=?', (task['id'],)).fetchone()[0])
        self.assertEqual((self.repo / 'module.py').read_text(), 'value = 9\n')

    def test_final_checkpoint_blocks_without_reopening_and_invalidates_on_change(self):
        plan = self._plan(policy=True)
        plan['tasks'] = [plan['tasks'][0]]
        plan['validation_policy']['final_tests'] = [['python3', '-m', 'unittest', 'tests.test_core']]
        job, task = self._submit(plan)
        head = core.git(self.repo, 'rev-parse', 'HEAD')
        with core.database() as db:
            db.execute("UPDATE tasks SET state='done',phase='integrate',attempt=4,commit_sha=?,result='{}' WHERE id=?", (head, task['id']))
        calls = []

        def fail(_cwd, commands, timeout=120):
            calls.append(list(commands))
            return [{'command': command, 'exit_code': 1, 'stderr': ('x' * 5000) + 'final boom'} for command in commands]

        with patch.object(core, 'bridge', return_value={}), patch.object(core, 'test_commands', side_effect=fail):
            core.tick()
        with core.database() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?', (job['id'],)).fetchone()[0], 'blocked')
            row = dict(db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone())
            blocked = self._events(db, job['id'], 'final_validation_blocked')[-1][1]
            proof = self._events(db, job['id'], 'final_validation')[-1][1]
            kinds = [kind for kind, _data in self._events(db, job['id'])]
        self.assertEqual(calls, [plan['validation_policy']['final_tests']])
        self.assertEqual(row['state'], 'done')
        self.assertEqual(row['attempt'], 4)
        self.assertEqual(row['commit_sha'], head)
        self.assertEqual(core.git(self.repo, 'rev-parse', 'HEAD'), head)
        self.assertTrue(proof['passed'] is False)
        self.assertEqual(proof['counts']['executed'], 1)
        self.assertIn('final boom', blocked['error'])
        self.assertNotIn('x' * 2000, blocked['error'])
        self.assertLess(len(blocked['error']), 4000)
        self.assertNotIn('job_completed', kinds)
        with patch.object(core, 'bridge', return_value={}), patch.object(core, 'test_commands', side_effect=fail):
            core.tick()
        self.assertEqual(len(calls), 1)
        with core.database() as db:
            self.assertEqual(db.execute('SELECT state,attempt FROM tasks WHERE id=?', (task['id'],)).fetchone()['attempt'], 4)

        (self.repo / 'module.py').write_text('value = 2\n')
        core.git(self.repo, 'add', 'module.py')
        core.git(self.repo, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'later')
        changed = core.git(self.repo, 'rev-parse', 'HEAD')
        self.assertNotEqual(changed, head)
        with core.database() as db:
            db.execute("UPDATE jobs SET state='running',notified=0 WHERE id=?", (job['id'],))
        calls.clear()

        def ok(_cwd, commands, timeout=120):
            calls.append(list(commands))
            return [{'command': command, 'exit_code': 0} for command in commands]

        with patch.object(core, 'bridge', return_value={}), patch.object(core, 'test_commands', side_effect=ok):
            core.tick()
        with core.database() as db:
            db.execute("UPDATE jobs SET state='running',notified=0 WHERE id=?", (job['id'],))
        with patch.object(core, 'bridge', return_value={}), patch.object(core, 'test_commands', side_effect=ok):
            core.tick()
        self.assertEqual(len(calls), 1)
        with core.database() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?', (job['id'],)).fetchone()[0], 'done')
            self.assertEqual(db.execute('SELECT state,attempt,commit_sha FROM tasks WHERE id=?', (task['id'],)).fetchone()['commit_sha'], head)
            actions = [data['action'] for _kind, data in self._events(db, job['id'], 'final_validation') if data.get('passed')]
        self.assertEqual(actions[-2:], ['executed', 'reused'])

    def test_prompts_split_one_essential_round_from_justified_review(self):
        legacy_job = {'objective': 'Legacy', 'plan': core.encoded(self.legacy), 'cwd': str(self.repo)}
        opt_job = {'objective': 'Opt-in', 'plan': core.encoded(self.optin)}
        spec = self.optin['tasks'][0]
        task = {'cwd': str(self.repo), 'phase': 'implement', 'error': ''}
        legacy = core.prompt_for(legacy_job, task, self.legacy['tasks'][0])
        self.assertIn('Implemente a tarefa e corrija quaisquer falhas. Contexto de tentativa anterior:', legacy)
        self.assertNotIn('Modo proporcional', legacy)
        opted = core.prompt_for(opt_job, task, spec)
        self.assertIn('implemente primeiro o bloco funcional completo', opted)
        self.assertIn('uma única rodada dos checks essenciais', opted)
        self.assertIn('somente se um falhar', opted)
        self.assertIn('Não alegue economia percentual de tokens', opted)
        review = dict(task)
        review['phase'] = 'review'
        legacy_review = core.prompt_for(legacy_job, review, self.legacy['tasks'][0])
        self.assertIn('execute testes relevantes', legacy_review)
        opted_review = core.prompt_for(opt_job, review, spec)
        self.assertIn('Não modifique o código', opted_review)
        self.assertIn('Não repita a bateria essencial por padrão', opted_review)
        self.assertIn('justificativa técnica', opted_review)
        self.assertNotIn('execute testes relevantes', opted_review)

    def test_unverified_runner_blocks_final_checkpoint(self):
        plan = self._plan(policy=True)
        plan['tasks'] = [plan['tasks'][0]]
        job, task = self._submit(plan)
        head = core.git(self.repo, 'rev-parse', 'HEAD')
        with core.database() as db:
            db.execute("UPDATE tasks SET state='done',attempt=2,commit_sha=? WHERE id=?", (head, task['id']))
        with patch.object(core, 'bridge', return_value={}), patch.object(core, 'runner_stamp', return_value=None), patch.object(core, 'test_commands') as tests:
            core.tick()
            tests.assert_not_called()
        with core.database() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?', (job['id'],)).fetchone()[0], 'blocked')
            self.assertEqual(db.execute('SELECT state,attempt FROM tasks WHERE id=?', (task['id'],)).fetchone()['state'], 'done')
            reason = self._events(db, job['id'], 'final_validation_blocked')[-1][1]['error']
        self.assertIn('não verificável', reason)

    def _image(self, image_id, digests=None):
        def inspector(image):
            self.assertEqual(image, RUNNER_IMAGE)
            payload = {'id': image_id}
            if digests is not None:
                payload['digests'] = digests
            return payload
        return inspector

    def _evidence(self, stamp):
        commands = [['python3', '-m', 'unittest', 'test_first']]
        return {
            'passed': True,
            'digest': 'source',
            'commands': commands,
            'runner': stamp,
            'checks': [{'command': commands[0], 'exit_code': 0, 'status': 'passed'}],
        }

    def test_runner_identity_tracks_image_and_node_bytes(self):
        blob = b'\x7fELF-node-content-v1'
        host = self.root / 'host-node'
        other = self.root / 'other-path-node'
        mounted = self.root / 'mounted-node'
        absent = self.root / 'absent-node'
        host.write_bytes(blob)
        other.write_bytes(blob)
        mounted.write_bytes(blob)
        image_a = 'sha256:' + '11' * 32
        image_b = 'sha256:' + '22' * 32
        digest_a = 'sha256:' + '33' * 32
        digest_b = 'sha256:' + '44' * 32
        inspector = self._image(image_a, [digest_a])
        kwargs = {'image_inspector': inspector, 'mounted_node': str(absent)}

        selected = runner_stamp(self.repo, str(host), **kwargs)
        same_bytes = runner_stamp(self.repo, str(other), **kwargs)
        via_mount = runner_stamp(self.repo, str(absent), image_inspector=inspector, mounted_node=str(mounted))
        self.assertIsNotNone(selected)
        self.assertEqual(set(selected), {'id', 'image'})
        self.assertEqual(selected['image'], RUNNER_IMAGE)
        self.assertEqual(selected['id'], same_bytes['id'])
        self.assertEqual(selected['id'], via_mount['id'])
        self.assertNotIn(str(host), json.dumps(selected))
        self.assertNotIn(str(mounted), json.dumps(via_mount))

        os.utime(host, (10, 10))
        retimed = runner_stamp(self.repo, str(host), **kwargs)
        self.assertEqual(selected['id'], retimed['id'])
        host.write_bytes(blob + b'\x00changed')
        changed_bytes = runner_stamp(self.repo, str(host), **kwargs)
        self.assertNotEqual(selected['id'], changed_bytes['id'])

        retagged = runner_stamp(self.repo, str(other), image_inspector=self._image(image_b, [digest_a]), mounted_node=str(absent))
        self.assertEqual(retagged['image'], selected['image'])
        self.assertNotEqual(selected['id'], retagged['id'])
        redigest = runner_stamp(self.repo, str(other), image_inspector=self._image(image_a, [digest_b, digest_a]), mounted_node=str(absent))
        reordered = runner_stamp(self.repo, str(other), image_inspector=self._image(image_a, [digest_a, digest_b]), mounted_node=str(absent))
        self.assertNotEqual(selected['id'], redigest['id'])
        self.assertEqual(redigest['id'], reordered['id'])

        link = self.root / 'linked-node'
        link.symlink_to(other)
        linked = runner_stamp(self.repo, str(link), **kwargs)
        self.assertEqual(linked['id'], same_bytes['id'])

        evidence = self._evidence(selected)
        commands = evidence['commands']
        self.assertTrue(reuse_decision(evidence, digest='source', commands=commands, runner=selected)[0])
        self.assertFalse(reuse_decision(evidence, digest='source', commands=commands, runner=changed_bytes)[0])
        self.assertFalse(reuse_decision(evidence, digest='source', commands=commands, runner=retagged)[0])
        self.assertFalse(reuse_decision(evidence, digest='source', commands=commands, runner=None)[0])
        proof = {'passed': True, 'head': 'head', 'digest': 'source', 'commands': commands, 'runner': selected}
        self.assertTrue(proof_valid(proof, head='head', digest='source', commands=commands, runner=selected))
        self.assertFalse(proof_valid(proof, head='head', digest='source', commands=commands, runner=retagged))
        self.assertFalse(proof_valid(proof, head='head', digest='source', commands=commands, runner=None))

        self.assertIsNone(runner_stamp(self.repo, str(absent), image_inspector=inspector, mounted_node=str(absent)))
        self.assertIsNone(runner_stamp(self.repo, str(other), image_inspector=lambda image: None, mounted_node=str(absent)))
        self.assertIsNone(runner_stamp(self.repo, str(other), image_inspector=lambda image: {'id': 'latest'}, mounted_node=str(absent)))
        self.assertIsNone(runner_stamp(self.repo, str(self.root), image_inspector=inspector, mounted_node=str(self.root)))
        unreadable = self.root / 'locked-node'
        unreadable.write_bytes(blob)
        real_open = Path.open

        def fail_open(path, *args, **kwargs):
            if path == unreadable:
                raise OSError('unreadable node')
            return real_open(path, *args, **kwargs)

        with patch.object(Path, 'open', fail_open):
            self.assertIsNone(runner_stamp(self.repo, str(unreadable), image_inspector=inspector, mounted_node=str(absent)))

        with patch.dict(os.environ, {'PASEO_RUNNER_IMAGE_ID': image_b, 'PASEO_RUNNER_STAMP': 'bypass'}):
            stamped = runner_stamp(self.repo, str(other), **kwargs)
        self.assertEqual(stamped['id'], same_bytes['id'])
        self.assertNotEqual(stamped['id'], 'bypass')
        self.assertNotIn(image_b, json.dumps(stamped))

    def test_local_image_inspect_is_read_only_and_fail_closed(self):
        self.image_fixture.stop()
        image_id = 'sha256:' + 'ab' * 32
        digest = 'sha256:' + 'cd' * 32
        calls = []

        class Proc:
            def __init__(self, code, stdout):
                self.returncode = code
                self.stdout = stdout
                self.stderr = ''

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return Proc(0, image_id + '\n' + json.dumps([f'registry.local/runtime@{digest}']) + '\n')

        try:
            with patch.dict(os.environ, {'PASEO_RUNNER_IMAGE_ID': 'sha256:' + 'ff' * 32}):
                info = inspect_local_image(RUNNER_IMAGE, run=fake_run)
            self.assertEqual(info, {'id': image_id, 'digests': [digest]})
            argv, kwargs = calls[0]
            self.assertEqual(argv[:3], ['docker', 'image', 'inspect'])
            self.assertEqual(argv[-1], RUNNER_IMAGE)
            self.assertNotIn('pull', argv)
            self.assertNotIn('--pull', argv)
            self.assertNotIn('ff' * 32, ' '.join(argv))
            self.assertEqual(kwargs.get('stdin'), subprocess.DEVNULL)
            self.assertNotIn('env', kwargs)

            self.assertIsNone(inspect_local_image(RUNNER_IMAGE, run=lambda argv, **kwargs: Proc(1, '')))
            self.assertIsNone(inspect_local_image(RUNNER_IMAGE, run=lambda argv, **kwargs: (_ for _ in ()).throw(OSError('no socket'))))
            self.assertIsNone(inspect_local_image(RUNNER_IMAGE, run=lambda argv, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(argv, 15))))
            self.assertIsNone(inspect_local_image(RUNNER_IMAGE, run=lambda argv, **kwargs: Proc(0, 'not-an-id\n[]\n')))
            self.assertIsNone(inspect_local_image(RUNNER_IMAGE, run=lambda argv, **kwargs: Proc(0, image_id + '\n' + json.dumps(['not-a-digest']) + '\n')))
            self.assertIsNone(inspect_local_image('-evil', run=fake_run))
            self.assertEqual(len(calls), 1)

            node = self.root / 'inspect-node'
            node.write_bytes(b'node-bytes')
            absent = self.root / 'missing-mount'

            def fail_run(argv, **kwargs):
                calls.append((argv, kwargs))
                raise OSError('socket unavailable')

            with patch.object(validation.subprocess, 'run', fail_run):
                stamp = runner_stamp(self.repo, str(node), mounted_node=str(absent))
            failed, reason = reuse_decision(self._evidence({'id': 'previous', 'image': RUNNER_IMAGE}), digest='source', commands=[['python3', '-m', 'unittest', 'test_first']], runner=stamp)
            self.assertIsNone(stamp)
            self.assertFalse(failed)
            self.assertIn('não verificável', reason)
            self.assertTrue(any(item[0][:3] == ['docker', 'image', 'inspect'] for item in calls[1:]))
            self.assertFalse(any('pull' in arg for item in calls[1:] for arg in item[0]))
        finally:
            self.image_fixture.start()


if __name__ == '__main__':
    unittest.main()
