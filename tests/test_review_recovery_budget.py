import json
import unittest
from tests import test_resume
from orchestrator import core

class RecoveryBudgetTests(unittest.TestCase):
    setUp=test_resume.ResumeTests.setUp
    tearDown=test_resume.ResumeTests.tearDown

    def prepare(self, state='blocked'):
        (self.root/'autonomy.json').write_text('{"unattended_development":true}')
        with core.database() as db:
            spec=json.loads(db.execute('SELECT spec FROM tasks WHERE id=?',(self.paused_id,)).fetchone()[0]);spec['max_attempts']=5
            error='Revisão reprovou: '+json.dumps({'decision':'fail','issues':[{'file':'module.py','requested_change':'Use isolated subscriber fixture','title':'Duplicate subscriber'}]})
            db.execute('UPDATE jobs SET state=? WHERE id=?',(state,self.job_id))
            db.execute("UPDATE tasks SET spec=?,state='blocked',phase='implement',attempt=5,error=? WHERE id=?",(json.dumps(spec),error,self.paused_id))
            return spec,error

    def test_manager_recovers_sixth_attempt_with_feedback_and_done_preserved(self):
        spec,error=self.prepare();spec['max_attempts']=6
        core.recover(self.job_id,'Fix isolated fixture identified by independent review',spec)
        with core.database() as db:
            task=db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone()
            self.assertEqual(task['attempt'],5);self.assertEqual(task['error'],error);self.assertEqual(task['state'],'queued')
            self.assertEqual(db.execute('SELECT state FROM tasks WHERE id=?',(self.done_id,)).fetchone()[0],'done')
            self.assertEqual(task['cwd'],str(self.work))

    def test_new_finding_extends_once_but_duplicate_does_not(self):
        spec,error=self.prepare('running')
        with core.database() as db:
            task=db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone()
            self.assertTrue(core.extend_review_budget(db,task,error))
            self.assertFalse(core.extend_review_budget(db,task,error))
            self.assertEqual(json.loads(db.execute('SELECT spec FROM tasks WHERE id=?',(self.paused_id,)).fetchone()[0])['max_attempts'],6)
            self.assertEqual(db.execute('SELECT attempt FROM tasks WHERE id=?',(self.paused_id,)).fetchone()[0],5)

    def test_pause_and_unstructured_failure_do_not_extend(self):
        spec,error=self.prepare('paused')
        with core.database() as db:
            task=db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone()
            self.assertFalse(core.extend_review_budget(db,task,error))
            self.assertFalse(core.extend_review_budget(db,task,'network failure'))

    def test_recovery_cannot_bulk_allocate_attempts(self):
        spec,error=self.prepare();spec['max_attempts']=100
        with self.assertRaisesRegex(ValueError,'uma tentativa'):core.recover(self.job_id,'fix',spec)
