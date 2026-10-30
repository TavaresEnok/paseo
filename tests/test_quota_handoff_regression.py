import json,unittest
from unittest.mock import patch
from tests import test_resume
from orchestrator import core,policy_integration as pi

class QuotaHandoffTests(unittest.TestCase):
 setUp=test_resume.ResumeTests.setUp
 tearDown=test_resume.ResumeTests.tearDown
 def test_completion_quota_preserves_attempt_worktree_and_feedback(self):
  with core.database() as db:
   db.execute("UPDATE jobs SET state='running' WHERE id=?",(self.job_id,))
   db.execute("UPDATE tasks SET state='running',phase='implement',attempt=5,agent_id='worker',model='codex-programmer/gpt-6.1-terra' WHERE id=?",(self.paused_id,))
   task=db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone()
   with patch.object(pi,'policy_enabled',return_value=True),patch.object(pi,'record_role_exhaustion',return_value='codex-programmer'),patch.object(pi,'release_task') as release,patch.object(core,'archive_worker',return_value={'agent_id':'worker','archivedAt':'now'}),patch('orchestrator.model_limits.load_limits',return_value={'programming':{'fallback_allowed':True}}):
    core.failure(db,task,'Executor bloqueado: Individual quota reached')
    release.assert_called_once()
   after=db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone()
   self.assertEqual(after['state'],'queued');self.assertEqual(after['attempt'],5);self.assertEqual(after['cwd'],str(self.work));self.assertIsNone(after['agent_id']);self.assertTrue(after['error'].startswith('programmer_quota:'))
   self.assertEqual(db.execute('SELECT count(*) FROM outcomes WHERE task_id=?',(self.paused_id,)).fetchone()[0],0)
 def test_missing_archive_ack_does_not_launch_duplicate_or_release_worker(self):
  with core.database() as db:
   db.execute("UPDATE tasks SET state='running',phase='implement',agent_id='worker',model='codex-programmer/gpt-6.1-terra' WHERE id=?",(self.paused_id,))
   task=db.execute('SELECT * FROM tasks WHERE id=?',(self.paused_id,)).fetchone()
   with patch.object(pi,'policy_enabled',return_value=True),patch.object(pi,'record_role_exhaustion',return_value='codex-programmer'),patch.object(pi,'release_task') as release,patch.object(core,'archive_worker',return_value=None),patch('orchestrator.model_limits.load_limits',return_value={'programming':{'fallback_allowed':True}}):
    self.assertTrue(pi.programmer_quota_handoff(db,task,{'lastError':'usage limit reached'}));release.assert_not_called()
   self.assertEqual(db.execute('SELECT state,agent_id FROM tasks WHERE id=?',(self.paused_id,)).fetchone()[0],'running')
