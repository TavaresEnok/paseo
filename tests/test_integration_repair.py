import json,sqlite3,unittest
from unittest.mock import patch
from orchestrator import integration_owner as owner

class IntegrationRepair(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.executescript('''CREATE TABLE jobs(id TEXT PRIMARY KEY,state TEXT,approved INT,notified INT,updated REAL);
   CREATE TABLE tasks(id TEXT PRIMARY KEY,job_id TEXT,task_key TEXT,state TEXT,phase TEXT,commit_sha TEXT,error TEXT,updated REAL);
   CREATE TABLE integration_owners(repo TEXT PRIMARY KEY,job_id TEXT,task_id TEXT,acquired REAL);
   INSERT INTO jobs VALUES('j','running',1,0,0);
   INSERT INTO tasks VALUES('original','j','original-key','blocked','integrate','old','test failed',0);
   INSERT INTO tasks VALUES('repair','j','repair-key','integrating','integrate','new',NULL,0);
   INSERT INTO integration_owners VALUES('/tmp/test-repair-repo','j','original',0);''')
  self.job={'id':'j','repo':'/tmp/test-repair-repo','approved':1,'state':'running'}
  self.addCleanup(self.db.close)
 def task(self,key):return self.db.execute('SELECT * FROM tasks WHERE id=?',(key,)).fetchone()
 def owner(self):return self.db.execute('SELECT task_id FROM integration_owners').fetchone()[0]
 def test_handoff_restore_and_crash_reconciliation(self):
  self.assertFalse(owner.claim(self.db,self.task('repair'),self.job))
  with patch('orchestrator.core.validate_integration_recovery') as validate,patch('orchestrator.core.git'),patch('orchestrator.core.event'),patch('orchestrator.validation_jobs.context_running',return_value=False):
   owner.authorize_repair(self.db,self.job,self.task('original'),self.task('repair'),'reviewed fixture correction')
   self.assertEqual(validate.call_count,2);self.assertEqual(self.owner(),'repair')
   self.assertTrue(owner.authorize_repair(self.db,self.job,self.task('original'),self.task('repair'),'same')['idempotent'])
   self.assertFalse(owner.claim(self.db,self.task('original'),self.job))
   self.db.execute("UPDATE tasks SET state='done' WHERE id='repair'")
   # Simulate process exit after marking the repair done, before release().
   self.assertTrue(owner.claim(self.db,self.task('original'),self.job))
   self.assertEqual(self.owner(),'original');self.assertEqual(self.task('original')['state'],'integrating')
   self.assertIsNone(self.task('original')['error']);self.assertEqual(self.task('repair')['state'],'done')
 def test_no_unreviewed_or_running_handoff(self):
  with patch('orchestrator.core.validate_integration_recovery'),patch('orchestrator.core.git'),patch('orchestrator.core.event'),patch('orchestrator.validation_jobs.context_running',return_value=True):
   with self.assertRaises(ValueError):owner.authorize_repair(self.db,self.job,self.task('original'),self.task('repair'),'fix')
  self.assertEqual(self.owner(),'original')
  self.db.execute("UPDATE tasks SET state='queued' WHERE id='repair'")
  with self.assertRaises(ValueError):owner.authorize_repair(self.db,self.job,self.task('original'),self.task('repair'),'not reviewed')
  self.assertEqual(self.owner(),'original')
 def test_pause_preserved_after_repair_completion(self):
  with patch('orchestrator.core.validate_integration_recovery'),patch('orchestrator.core.git'),patch('orchestrator.core.event'),patch('orchestrator.validation_jobs.context_running',return_value=False):
   owner.authorize_repair(self.db,self.job,self.task('original'),self.task('repair'),'fix')
   self.db.execute("UPDATE jobs SET state='paused'");self.db.execute("UPDATE tasks SET state='paused' WHERE id='original'");self.db.execute("UPDATE tasks SET state='done' WHERE id='repair'")
   owner.release(self.db,self.task('repair'),self.job)
   self.assertEqual(self.owner(),'original');self.assertEqual(self.task('original')['state'],'paused')
