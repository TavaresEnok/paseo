"""Actual local HTTP broker + SQLite leases + controller ticket + native JS gate.

Provider inference is simulated. No live daemon, Docker, auth or paid calls.
"""
import copy,json,os,sqlite3,subprocess,tempfile,threading,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from orchestrator.account_broker import Broker,CoordinatorServer,CoordinatorHandler
from orchestrator.account_client import Client
from orchestrator.policy_integration import select_for_role,sign_ticket,verify_ticket
from orchestrator import model_limits

ROOT=Path(__file__).resolve().parents[1]
class ContingencyContract(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.token='temporary-test-fixture-only';(self.root/'token').write_text(self.token)
  self.limits=json.loads((ROOT/'config/model-limits.json').read_text());self.now=time.time()
  self.broker=Broker(self.root/'broker.sqlite3',self.token,account_id='fixture')
  self.server=CoordinatorServer(('127.0.0.1',0),self.broker,self.token)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
  self.client=Client({'url':f'http://127.0.0.1:{self.server.server_port}','host_id':'host-a','account_id':'fixture','token_file':str(self.root/'token')})
 def catalog(self,recovered=None):
  pairs={'codex':'gpt-6.1-terra','codex-programmer':self.limits['programmer_account']['model'],'claude':'claude-sonnet-5-5','grok':'grok-4.7','antigravity2':'gemini-3.8-flash-high'}
  models=[]
  for p,m in pairs.items():
   available=p in {'codex',recovered}
   models.append({'id':m,'provider':p,'available':True,'authenticated':True,'cost':{'kind':'subscription','verified':True,'additional_cost':0},'quota':{'observed_at':time.time(),'source':'official agy response' if p=='antigravity2' else 'fixture','status':'available' if available else 'exhausted','windows':[{'remaining_fraction':.5 if available else 0}]}})
  if self.limits.get('antigravity_sonnet',{}).get('enabled'):
   models.append({**models[-1], 'id':'claude-sonnet-5-5-medium','quota':{**models[-1]['quota'],'status':'exhausted','windows':[{'remaining_fraction':0}]}})
  return {'models':models}
 def grant(self,chat,task,expected='codex/gpt-6.1-terra'):
  self.client.register(chat,[{'task_id':task,'role':'programmer','request_id':task,'generation':1,'phase':'implement'}])
  return self.client.acquire(chat,task,'programmer',task,{'generation':1,'requested_model_key':expected,'requested_thinking_option':self.limits['programmer_account']['thinking'] if expected.startswith('codex-programmer/') else self.limits['programming']['emergency_original_account']['thinking_option'] if expected=='codex/gpt-6.1-terra' else 'medium' if 'gemini' not in expected else 'high'})
 def test_dedicated_account_uses_configured_sol_medium(self):
  catalog=self.catalog('codex-programmer');self.client.observe(catalog,self.limits)
  with patch.object(model_limits,'LIMITS_FILE',ROOT/'config/model-limits.json'):
   selected=select_for_role(catalog,{'specialty':'coding'},self.limits)['selected']
  self.assertEqual(selected['thinking_option_id'],'medium')
  grant=self.grant('sol-medium-chat','sol-medium-task','codex-programmer/gpt-6.1-sol')
  self.assertTrue(grant['granted'],grant);self.assertEqual(grant['thinking_option'],'medium')
  agent=str(uuid.uuid4());self.client.bind(grant['lease_id'],agent)
  cwd=self.root/'sol-work';cwd.mkdir()
  ticket=sign_ticket({'role':'programmer','provider':'codex-programmer','model':'gpt-6.1-sol','effort':'medium','agent_id':agent,'chat_id':'sol-medium-chat','request_id':'sol-medium-task','cwd':str(cwd),'decision_fp':'test'},self.token)
  admission=self.root/'sol-admission.sqlite3';db=sqlite3.connect(admission);db.execute('CREATE TABLE tickets(agent_id TEXT,ticket_json TEXT)');db.execute('INSERT INTO tickets VALUES(?,?)',(agent,json.dumps(ticket)));db.commit();db.close()
  flow=self.root/'sol-flow.sqlite3';db=sqlite3.connect(flow);db.execute('CREATE TABLE capacity_leases(agent_id TEXT,request_id TEXT,role TEXT,chat_id TEXT,status TEXT)');db.execute('INSERT INTO capacity_leases VALUES(?,?,?,?,?)',(agent,'sol-medium-task','programmer','sol-medium-chat','held'));db.commit();db.close()
  (self.root/'sol-limits.json').write_text(json.dumps(self.limits))
  env={**os.environ,'PASEO_MODEL_LIMITS':str(self.root/'sol-limits.json'),'PASEO_ADMISSION_DB':str(admission),'PASEO_FLOW_DB':str(flow),'PASEO_CAPACITY_TOKEN_FILE':str(self.root/'token'),'PASEO_POLICY_FILE':str(ROOT/'config/profiles.json'),'PASEO_AUTONOMY_FILE':str(ROOT/'config/autonomy.json'),'PASEO_POLICY_ROOTS':str(cwd),'PASEO_HOLD_FILE':str(self.root/'nonexistent-hold'),'PASEO_AGENT_ID':agent}
  script="import {assertTurnAdmission} from './policy/policy.mjs';import assert from 'node:assert/strict';assert.equal(assertTurnAdmission(process.env.PASEO_AGENT_ID,'codex-programmer','gpt-6.1-sol','medium'),'admitted');assert.throws(()=>assertTurnAdmission(process.env.PASEO_AGENT_ID,'codex-programmer','gpt-6.1-sol','high'));"
  subprocess.run(['node','--input-type=module','-e',script],env=env,cwd=ROOT,check=True,capture_output=True,text=True)
  import importlib.util
  spec=importlib.util.spec_from_file_location('isolated_sol',ROOT/'native/isolated-provider.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertEqual(m.assert_cli_admission('codex-programmer',['app-server'],env),'programmer')
 def test_original_shared_cap_and_native_admission(self):
  catalog=self.catalog();self.client.observe(catalog,self.limits)
  with patch.object(model_limits,'LIMITS_FILE',ROOT/'config/model-limits.json'):
   selected=select_for_role(catalog,{'specialty':'coding'},self.limits)['selected']
  self.assertEqual(selected['key'],'codex/gpt-6.1-terra')
  grants=[]
  # Two separate chats/hosts compete for the same original account budget.
  for i in range(4):
   g=self.grant('chat-'+str(i%2),'task-'+str(i));self.assertTrue(g['granted'],g);grants.append(g)
  denied=self.grant('third-chat','fifth');self.assertFalse(denied['granted']);self.assertEqual(denied['reason'],'account_programmer_cap')
  agent=str(uuid.uuid4());self.client.bind(grants[0]['lease_id'],agent)
  cwd=self.root/'worktree';cwd.mkdir()
  ticket=sign_ticket({'role':'programmer','provider':'codex','model':'gpt-6.1-terra','effort':selected['thinking_option_id'],'agent_id':agent,'chat_id':'chat-0','request_id':'task-0','cwd':str(cwd),'decision_fp':'test'},self.token)
  self.assertTrue(verify_ticket(ticket,self.token));self.assertFalse(verify_ticket({**ticket,'effort':'medium' if ticket['effort']=='high' else 'high'},self.token))
  admission=self.root/'admission.sqlite3';db=sqlite3.connect(admission);db.execute('CREATE TABLE tickets(agent_id TEXT,ticket_json TEXT)');db.execute('INSERT INTO tickets VALUES(?,?)',(agent,json.dumps(ticket)))
  manager=sign_ticket({**ticket,'role':'manager','agent_id':'manager-fixture','model':'gpt-6.1-sol'},self.token);db.execute('INSERT INTO tickets VALUES(?,?)',('manager-fixture',json.dumps(manager)));db.commit();db.close()
  flow=self.root/'flow.sqlite3';db=sqlite3.connect(flow);db.execute('CREATE TABLE capacity_leases(agent_id TEXT,request_id TEXT,role TEXT,chat_id TEXT,status TEXT)');db.execute('INSERT INTO capacity_leases VALUES(?,?,?,?,?)',(agent,'task-0','programmer','chat-0','held'));db.commit();db.close()
  paths={'agent':agent,'cwd':str(cwd),'effort':ticket['effort']};(self.root/'fixture.json').write_text(json.dumps(paths));(self.root/'limits.json').write_text(json.dumps(self.limits))
  env={**os.environ,'PASEO_MODEL_LIMITS':str(self.root/'limits.json'),'PASEO_ADMISSION_DB':str(admission),'PASEO_FLOW_DB':str(flow),'PASEO_CAPACITY_TOKEN_FILE':str(self.root/'token'),'PASEO_POLICY_FILE':str(ROOT/'config/profiles.json'),'PASEO_AUTONOMY_FILE':str(ROOT/'config/autonomy.json'),'PASEO_POLICY_ROOTS':str(cwd),'PASEO_HOLD_FILE':str(self.root/'nonexistent-hold')}
  subprocess.run(['node',str(ROOT/'tests/node/admission-contract.mjs'),str(self.root/'fixture.json')],env=env,check=True,capture_output=True,text=True)
  # An unconfirmed end must not free a still-running worker's capacity.
  bad=self.client.release(grants[0]['lease_id'],{'kind':'completed','confirmed':False,'agent_id':agent});self.assertFalse(bad['released'])
  good=self.client.release(grants[0]['lease_id'],{'kind':'completed','confirmed':True,'agent_id':agent});self.assertTrue(good['released'])
 def test_antigravity_sonnet_own_quota_broker_and_native_gate(self):
  catalog=self.catalog();partner=catalog['models'][-1]
  partner['quota'].update(status='available',windows=[{'remaining_fraction':1}])
  self.client.observe(catalog,self.limits)
  expected='antigravity2/claude-sonnet-5-5-medium'
  with patch.object(model_limits,'LIMITS_FILE',ROOT/'config/model-limits.json'):
   selected=select_for_role(catalog,{'specialty':'coding'},self.limits)['selected']
  self.assertEqual(selected['key'],expected)
  grant=self.grant('chat-sonnet','task-sonnet',expected);self.assertTrue(grant['granted'],grant)
  agent=str(uuid.uuid4());self.client.bind(grant['lease_id'],agent)
  cwd=self.root/'work';cwd.mkdir()
  ticket=sign_ticket({'role':'programmer','provider':'antigravity2','model':'claude-sonnet-5-5-medium','effort':'medium','agent_id':agent,'chat_id':'chat-sonnet','request_id':'task-sonnet','cwd':str(cwd),'decision_fp':'test'},self.token)
  admission=self.root/'admission.sqlite3';db=sqlite3.connect(admission);db.execute('CREATE TABLE tickets(agent_id TEXT,ticket_json TEXT)');db.execute('INSERT INTO tickets VALUES(?,?)',(agent,json.dumps(ticket)));db.commit();db.close()
  flow=self.root/'flow.sqlite3';db=sqlite3.connect(flow);db.execute('CREATE TABLE capacity_leases(agent_id TEXT,request_id TEXT,role TEXT,chat_id TEXT,status TEXT)');db.execute('INSERT INTO capacity_leases VALUES(?,?,?,?,?)',(agent,'task-sonnet','programmer','chat-sonnet','held'));db.commit();db.close()
  (self.root/'limits.json').write_text(json.dumps(self.limits))
  env={**os.environ,'PASEO_MODEL_LIMITS':str(self.root/'limits.json'),'PASEO_ADMISSION_DB':str(admission),'PASEO_FLOW_DB':str(flow),'PASEO_CAPACITY_TOKEN_FILE':str(self.root/'token'),'PASEO_POLICY_FILE':str(ROOT/'config/profiles.json'),'PASEO_AUTONOMY_FILE':str(ROOT/'config/autonomy.json'),'PASEO_POLICY_ROOTS':str(cwd),'PASEO_HOLD_FILE':str(self.root/'nonexistent-hold'),'PASEO_AGENT_ID':agent}
  script="import {assertTurnAdmission} from './policy/policy.mjs';import assert from 'node:assert/strict';assert.equal(assertTurnAdmission(process.env.PASEO_AGENT_ID,'antigravity2','claude-sonnet-5-5-medium','medium'),'admitted');assert.throws(()=>assertTurnAdmission(process.env.PASEO_AGENT_ID,'antigravity2','claude-sonnet-5-5-medium','high'));"
  subprocess.run(['node','--input-type=module','-e',script],env=env,cwd=ROOT,check=True,capture_output=True,text=True)
  import importlib.util
  spec=importlib.util.spec_from_file_location('isolated',ROOT/'native/isolated-provider.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertEqual(m.assert_cli_admission('antigravity2',['--model','claude-sonnet-5-5-medium','--effort','medium'],env),'programmer')
  for args in [['--model','gemini-3.8-flash-high','--effort','high'],['--model','claude-sonnet-5-5-medium','--effort','high']]:
   with self.assertRaises(SystemExit):m.assert_cli_admission('antigravity2',args,env)
 def test_recovery_changes_new_work_preserves_running_lease(self):
  self.client.observe(self.catalog(),self.limits);g=self.grant('chat','emergency');self.assertTrue(g['granted'],g)
  self.client.bind(g['lease_id'],'running-emergency-agent')
  self.client.observe(self.catalog('codex-programmer'),self.limits)
  new=self.grant('chat','next','codex-programmer/'+self.limits['programmer_account']['model']);self.assertTrue(new['granted'],new)
  with sqlite3.connect(self.root/'broker.sqlite3') as db:
   row=db.execute('SELECT state,bound_agent_id FROM leases WHERE lease_id=?',(g['lease_id'],)).fetchone()
   self.assertEqual(row,('held','running-emergency-agent'))
if __name__=='__main__':unittest.main()
