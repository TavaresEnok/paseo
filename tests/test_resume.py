import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orchestrator import core


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.repo=self.root/'workspace'/'repo'
        self.repo.mkdir(parents=True)
        self.work=self.root/'worktrees'/'task'
        self.work.mkdir(parents=True)
        self.state=self.root/'state'
        self.patches=[
            patch.object(core,'archive_worker'),
            patch.object(core,'STATE',self.state),
            patch.object(core,'DEV',self.root/'workspace'),
            patch.object(core,'WORKTREES',self.root/'worktrees'),
            patch.object(core,'AUTONOMY_FILE',self.root/'autonomy.json'),
            patch.dict(os.environ,{},clear=False),
        ]
        for item in self.patches:item.start()
        self.old=os.environ.pop('PASEO_AGENT_ID',None)
        core.git(self.repo,'init')
        core.git(self.repo,'symbolic-ref','HEAD','refs/heads/main')
        (self.repo/'module.py').write_text('value = 1\n')
        core.git(self.repo,'add','.')
        core.git(self.repo,'-c','user.name=Test','-c','user.email=test@localhost','commit','-m','baseline')
        self.plan={'objective':'Resume plan','repo':str(self.repo),'tasks':[
            {'id':'first','objective':'Done work','acceptance':['kept'],'allowed_files':['module.py'],'tests':[['python3','-m','unittest']],'timeout_seconds':60,'max_attempts':3},
            {'id':'second','objective':'Continue work','acceptance':['kept'],'allowed_files':['module.py'],'tests':[['python3','-m','unittest']],'timeout_seconds':60,'max_attempts':3,'depends_on':['first']}]}
        result=core.submit(self.plan,supervisor_id='supervisor-fixture')
        core.approve(result['job_id'],reason='approved for resume tests')
        self.job_id=result['job_id']
        with core.database() as db:
            self.job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(self.job_id,)).fetchone())
            rows=db.execute('SELECT * FROM tasks WHERE job_id=? ORDER BY rowid',(self.job_id,)).fetchall()
            self.done_id,self.paused_id=rows[0]['id'],rows[1]['id']
            db.execute("UPDATE tasks SET state='done',attempt=1,phase='implement',cwd=?,workspace_id=?,result=? WHERE id=?",
                       (str(self.work), 'ws-done', '{"status":"completed"}', self.done_id))
            db.execute("UPDATE tasks SET state='paused',attempt=2,phase='review',cwd=?,workspace_id=?,branch=? WHERE id=?",
                       (str(self.work), 'ws-open', 'task/same', self.paused_id))
            db.execute("UPDATE jobs SET state='paused' WHERE id=?",(self.job_id,))
            db.execute('''INSERT INTO jobs(id,objective,repo,branch,plan,plan_hash,state,supervisor_id,created,approved,approval,updated,notified)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       ('other-paused','other',self.job['repo'],'orchestration/other',self.job['plan'],'other-hash','paused','supervisor-fixture',core.now(),core.now(),'{}',core.now(),0))
        (self.work/'notes.md').write_text('keep\n')
        (self.work/'.paseo-result.json').write_text('{"status":"completed"}\n')

    def tearDown(self):
        if self.old is not None:os.environ['PASEO_AGENT_ID']=self.old
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()

    def test_wrong_owner_does_not_resume(self):
        with self.assertRaisesRegex(ValueError,'supervisor deste plano'):
            core.resume(self.job_id,'continue',caller_agent_id='someone-else')
        with core.database() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(self.job_id,)).fetchone()[0],'paused')
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',('other-paused',)).fetchone()[0],'paused')

    def test_resume_preserves_done_attempt_and_worktree(self):
        with core.database() as db:
            db.execute("INSERT INTO outcomes(model,task_id,success,latency,at) VALUES(?,?,?,?,?)",('grok/grok-4.7',self.paused_id,0,3,core.now()))
            db.execute('INSERT INTO tasks(id,job_id,task_key,spec,state,attempt,phase,updated) VALUES(?,?,?,?,?,?,?,?)',
                       ('queued-1',self.job_id,'third',self.job['plan'],'queued',0,'implement',core.now()))
            before=db.execute('SELECT count(*) FROM events').fetchone()[0]
        with patch.object(core,'native_snapshot',return_value={'status':'idle'}) as snap:
            result=core.resume(self.job_id,'usuário autorizou continuar o plano')
            snap.assert_not_called()
        self.assertEqual(result['state'],'running')
        self.assertEqual(result['resumed_tasks'],['second'])
        with core.database() as db:
            done=dict(db.execute('SELECT * FROM tasks WHERE id=?',(self.done_id,)).fetchone())
            paused=dict(db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone())
            self.assertEqual(done['state'],'done')
            self.assertEqual(done['attempt'],1)
            self.assertEqual(done['cwd'],str(self.work))
            self.assertEqual(paused['state'],'queued')
            self.assertEqual(paused['phase'],'review')
            self.assertEqual(paused['attempt'],2)
            self.assertEqual(paused['cwd'],str(self.work))
            self.assertEqual(paused['workspace_id'],'ws-open')
            self.assertEqual(paused['branch'],'task/same')
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',('other-paused',)).fetchone()[0],'paused')
            self.assertEqual(tuple(db.execute("SELECT state,attempt FROM tasks WHERE id='queued-1'").fetchone()),('queued',0))
            self.assertEqual(db.execute('SELECT count(*) FROM outcomes').fetchone()[0],1)
            self.assertGreater(db.execute('SELECT count(*) FROM events').fetchone()[0],before)
        self.assertEqual((self.work/'notes.md').read_text(),'keep\n')
        self.assertTrue((self.work/'.paseo-result.json').exists())
        again=core.resume(self.job_id,'segunda chamada é o mesmo plano running')
        self.assertTrue(again['idempotent'])
        with core.database() as db:
            self.assertEqual(db.execute('SELECT attempt FROM tasks WHERE id=?',(self.paused_id,)).fetchone()[0],2)

    def test_pending_launch_receipt_is_not_replayed_by_resume(self):
        receipt={'idempotencyKey':'flow-same','provider':'grok','model':'grok-4.7','cwd':str(self.work)}
        with core.database() as db:
            db.execute("UPDATE tasks SET agent_id=?,launch_request=?,attempt=2,phase='implement' WHERE id=?",
                       ('old-worker',json.dumps(receipt),self.paused_id))
        calls=[]
        def native(agent_id):
            calls.append(agent_id)
            return {'status':'idle'}
        with patch.object(core,'native_snapshot',side_effect=native),patch.object(core,'bridge') as bridge:
            result=core.resume(self.job_id,'retomar com o recibo já gravado')
            bridge.assert_not_called()
        self.assertEqual(calls,['old-worker'])
        self.assertEqual(result['receipts_preserved'],['second'])
        with core.database() as db:
            row=dict(db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone())
        self.assertEqual(row['state'],'queued')
        self.assertEqual(row['attempt'],2)
        self.assertEqual(row['agent_id'],'old-worker')
        self.assertEqual(json.loads(row['launch_request']),receipt)
        self.assertEqual(row['cwd'],str(self.work))

    def test_exhausted_paused_task_gains_one_attempt_until_five(self):
        with core.database() as db:
            db.execute("UPDATE tasks SET attempt=3,phase='implement',agent_id=NULL,launch_request=NULL WHERE id=?",(self.paused_id,))
            old_hash=db.execute('SELECT plan_hash FROM jobs WHERE id=?',(self.job_id,)).fetchone()[0]
        result=core.resume(self.job_id,'autorização explícita para mais uma tentativa')
        self.assertEqual(result['attempt_extensions'],[{'task_key':'second','attempt':3,'max_attempts':4}])
        with core.database() as db:
            row=dict(db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone())
            job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(self.job_id,)).fetchone())
            event=json.loads(db.execute("SELECT data FROM events WHERE kind='job_resumed'").fetchone()[0])
        self.assertEqual(row['attempt'],3)
        self.assertEqual(row['state'],'queued')
        self.assertEqual(json.loads(row['spec'])['max_attempts'],4)
        self.assertNotEqual(job['plan_hash'],old_hash)
        self.assertEqual(event['reason'],'autorização explícita para mais uma tentativa')
        self.assertEqual(event['plan_hash'],job['plan_hash'])
        self.assertEqual(event['previous_plan_hash'],old_hash)
        with core.database() as db:
            db.execute("UPDATE jobs SET state='paused' WHERE id=?",(self.job_id,))
            db.execute("UPDATE tasks SET state='paused',attempt=5 WHERE id=?",(self.paused_id,))
            spec=json.loads(db.execute('SELECT spec FROM tasks WHERE id=?',(self.paused_id,)).fetchone()[0])
            spec['max_attempts']=5
            plan=json.loads(job['plan'])
            for item in plan['tasks']:
                if item['id']=='second':item['max_attempts']=5
            db.execute('UPDATE tasks SET spec=? WHERE id=?',(json.dumps(spec),self.paused_id))
            db.execute('UPDATE jobs SET plan=? WHERE id=?',(json.dumps(plan),self.job_id))
        core.resume(self.job_id,'continuação explícita com uma tentativa adicional após cinco')
        with core.database() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(self.job_id,)).fetchone()[0],'running')
            self.assertEqual(db.execute('SELECT attempt FROM tasks WHERE id=?',(self.paused_id,)).fetchone()[0],5)
            self.assertEqual(json.loads(db.execute('SELECT spec FROM tasks WHERE id=?',(self.paused_id,)).fetchone()[0])['max_attempts'],6)

    def test_busy_agent_and_canceled_plan_are_refused(self):
        with core.database() as db:
            db.execute("UPDATE tasks SET agent_id='old-worker' WHERE id=?",(self.paused_id,))
        with patch.object(core,'native_snapshot',return_value={'status':'running','activeTurn':True}),patch.object(core,'bridge') as bridge:
            with self.assertRaisesRegex(ValueError,'ocupado'):
                core.resume(self.job_id,'não duplicar executor')
            bridge.assert_not_called()
        with core.database() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(self.job_id,)).fetchone()[0],'paused')
            db.execute("UPDATE jobs SET state='canceled' WHERE id=?",(self.job_id,))
        with self.assertRaisesRegex(ValueError,'cancelado'):
            core.resume(self.job_id,'não reabrir cancelado')
