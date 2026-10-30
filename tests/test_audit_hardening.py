import copy,importlib.util,json,sqlite3,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from orchestrator.task_risk import assess,previous_review_findings
from orchestrator.manager_effort import choose
from orchestrator.recovery_budget import charge,assert_recoverable
from orchestrator.notifications import deliver
from orchestrator import policy_runtime as runtime

ROOT=Path(__file__).resolve().parents[1]
class RiskTests(unittest.TestCase):
 def test_sensitive_normal_structural(self):
  for path in ['src/auth/login.ts','backend/payments/service.go','db/migrations/002.sql','internal/tenant/dispatch.go']:
   self.assertEqual(assess({'allowed_files':[path]})['level'],'high',path)
  self.assertEqual(assess({'allowed_files':['ui/button.css'],'difficulty':2})['level'],'normal')
  self.assertEqual(choose('status',[],[{'id':'t','state':'running','spec':json.dumps({'criticality':'high'})}])['effort'],'medium')
  self.assertEqual(choose('continue',[{'id':'j','state':'running'}],[{'id':'t','state':'queued','spec':json.dumps({'criticality':'high'})}])['effort'],'high')
 def test_review_findings_survive_cleared_task_error(self):
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE events(task_id TEXT,kind TEXT,data TEXT)')
  db.execute('INSERT INTO events VALUES(?,?,?)',('t','correction_requested',json.dumps({'error':'Revisão reprovou: autorização incorreta'})))
  self.assertTrue(previous_review_findings(db,'t'));self.assertFalse(previous_review_findings(db,'other'))
 def test_reviewer_policy(self):
  limits=json.loads((ROOT/'config/model-limits.json').read_text());now=1000
  models=[]
  for provider in runtime.PROVIDERS:
   models.append({'provider':provider,'id':'fixture','authenticated':True,'available':True,'cost':{'verified':True,'kind':'subscription','additional_cost':0},'quota':{'source':'fixture','observed_at':now,'status':'available' if provider=='codex' else 'exhausted','windows':[{'remaining_fraction':.5 if provider=='codex' else 0}]}})
  for task,effort in [({'difficulty':2},'medium'),({'allowed_files':['auth/token.go']},'high'),({'review_findings':True},'high')]:
   result=runtime.evaluate('reviewer',{'models':models},limits,now=now,review_task=task)
   self.assertEqual(result['thinking_option'],effort,result)

class BudgetTests(unittest.TestCase):
 def test_stagnation_and_idempotency(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;s={'enabled':True,'max_same_failure':3,'max_automatic_attempts':8,'max_active_seconds':1000}
  task={'id':'t','agent_id':'a','attempt':1,'phase':'implement'}
  self.assertIsNone(charge(db,task,'same error',s,progress_digest='x'))
  charge(db,task,'same error',s,progress_digest='x');self.assertEqual(db.execute('SELECT failures FROM recovery_budgets').fetchone()[0],1)
  for attempt in [2,3]:
   task.update(attempt=attempt,agent_id=str(attempt));reason=charge(db,task,'same error',s,progress_digest='x')
  self.assertEqual(reason,'same_failure_without_progress')
  with self.assertRaises(ValueError):assert_recoverable(db,'t')
  assert_recoverable(db,'other')
 def test_progress_and_time(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;s={'enabled':True,'max_same_failure':2,'max_active_seconds':10}
  task={'id':'t','agent_id':'a','attempt':1,'phase':'implement'}
  charge(db,task,'error',s,active_seconds=4,progress_digest='first')
  task.update(attempt=2,agent_id='b')
  self.assertEqual(charge(db,task,'error',s,active_seconds=7,progress_digest='changed'),'active_time_budget')

class ReceiptTests(unittest.TestCase):
 def setup_case(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
  db.execute('CREATE TABLE jobs(id TEXT,state TEXT,updated REAL,notified INT,supervisor_id TEXT)');db.execute("INSERT INTO jobs VALUES('j','blocked',1,0,'chat')")
  return db
 def test_lost_reply_confirmed_by_receiver_no_duplicate(self):
  db=self.setup_case();clock=[1];sends=[]
  def bridge(action,**kw):
   if action=='send':sends.append(kw);raise OSError('reply lost after acceptance')
   if action=='message-receipt':return {'state':'completed'}
   self.fail(action)
  core=SimpleNamespace(now=lambda:clock[0],report=lambda j:None,bridge=bridge,event=lambda *a:None)
  rows=lambda:db.execute('SELECT * FROM jobs WHERE notified=0').fetchall()
  deliver(db,rows(),core);clock[0]=4;deliver(db,rows(),core)
  self.assertEqual(len(sends),1);self.assertEqual(db.execute('SELECT notified FROM jobs').fetchone()[0],1)
 def test_unknown_receiver_not_bypassed(self):
  db=self.setup_case();clock=[1];sends=[];events=[]
  def bridge(action,**kw):
   if action=='send':sends.append(kw);raise OSError('unknown outcome')
   if action=='message-receipt':return {'state':'pending'}
   if action=='timeline':return {'entries':[{'item':{'type':'assistant_message','text':sends[0]['options']['messageId']}}]}
   self.fail(action)
  core=SimpleNamespace(now=lambda:clock[0],report=lambda j:None,bridge=bridge,event=lambda *a:events.append(a))
  rows=lambda:db.execute('SELECT * FROM jobs WHERE notified=0').fetchall()
  deliver(db,rows(),core);clock[0]=4;deliver(db,rows(),core);clock[0]=400;deliver(db,rows(),core)
  self.assertEqual(len(sends),1);self.assertEqual(db.execute('SELECT delivery_state FROM notification_outbox').fetchone()[0],'needs_attention')
  self.assertEqual(sum(e[1]=='notification_delivery_uncertain' for e in events),1)

class NetworkPlanTests(unittest.TestCase):
 def test_private_destinations_and_no_live_execution(self):
  spec=importlib.util.spec_from_file_location('network_plan',ROOT/'deploy/hardening/prepare-worker-network.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  p=module.plan();self.assertFalse(p['ipv6']);self.assertIn('169.254.0.0/16',p['forward_rules']);self.assertIn('10.0.0.0/8',p['forward_rules']);self.assertEqual(p['input_rule'][-1],'DROP')
if __name__=='__main__':unittest.main()
