import copy,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from orchestrator import policy_integration as p,supervision as s

class StableManager(unittest.TestCase):
 def decision(self,model='gpt-6.1-sol',effort='medium'):
  return {'selected':{'provider':'codex','id':model,'thinking_option_id':effort},'reason':'first','gpt_only':False}
 def ticket(self,fp):
  return dict(agent_id='public',request_id='stable',chat_id='chat',role='manager',provider='codex',model='gpt-6.1-sol',effort='medium',cwd='/tmp',decision_fp=fp,mac='fixture')
 def test_informational_change_does_not_revoke_effective_grant(self):
  a=self.decision();b=copy.deepcopy(a);b.update(reason='fresh_catalog',gpt_only=True)
  self.assertEqual(p.decision_fingerprint(a),p.decision_fingerprint(b))
  b['selected']['thinking_option_id']='high';self.assertNotEqual(p.decision_fingerprint(a),p.decision_fingerprint(b))
  b=self.decision('gpt-6-astra');self.assertNotEqual(p.decision_fingerprint(a),p.decision_fingerprint(b))
 def test_safety_limits_of_stable_identity(self):
  primary={'provider':'codex'}
  self.assertTrue(p.stable_codex_manager(primary,self.decision('gpt-6-astra')['selected']))
  self.assertFalse(p.stable_codex_manager(primary,self.decision('gpt-6-astra','high')['selected']))
  self.assertFalse(p.stable_codex_manager({'provider':'claude'},self.decision()['selected']))
 def test_ticket_and_decision_are_published_atomically(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'admission.sqlite3';p.mirror_manager_grant(path,'public',self.ticket('old'))
   broken=self.ticket('new');del broken['provider']
   with self.assertRaises(KeyError):p.mirror_manager_grant(path,'public',broken)
   with sqlite3.connect(path) as db:
    self.assertEqual(db.execute('SELECT fingerprint FROM current_decisions').fetchone()[0],'old')
    self.assertEqual(json.loads(db.execute('SELECT ticket_json FROM tickets').fetchone()[0])['decision_fp'],'old')
 def route_db(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
  db.execute('CREATE TABLE supervisor_routes(primary_id TEXT,active_id TEXT,state TEXT,pending TEXT,next_check REAL,updated REAL)')
  db.execute("INSERT INTO supervisor_routes VALUES('public','old','switching_model',?,0,0)",(json.dumps({'model':'gpt-6-astra','effort':'medium','previous':'old','prompt':None}),))
  return db
 def test_model_switch_preserves_public_identity_without_new_agent_or_turn(self):
  db=self.route_db();route=dict(db.execute('SELECT * FROM supervisor_routes').fetchone());route['generation']=5
  with patch.object(s.core,'bridge',return_value={}) as bridge,patch.object(s,'bind_jobs') as bind,patch.object(s.core,'event'):
   s.transition(db,route,{}, {})
   bridge.assert_called_once_with('manager-reconfigure',agentId='public',model='gpt-6-astra',effort='medium')
   bind.assert_called_once_with(db,'public','old','public')
  self.assertEqual(tuple(db.execute('SELECT active_id,state,pending FROM supervisor_routes').fetchone()),('public','primary',None))
 def test_lost_rpc_ack_keeps_exact_transition_instead_of_spawning(self):
  db=self.route_db();route=dict(db.execute('SELECT * FROM supervisor_routes').fetchone());route['generation']=5
  with patch.object(s.core,'bridge',side_effect=TimeoutError('lost ack')) as bridge,patch.object(s.core,'event'):
   s.transition(db,route,{}, {})
  fresh=dict(db.execute('SELECT * FROM supervisor_routes').fetchone())
  self.assertEqual(fresh['state'],'switching_model');self.assertEqual(fresh['pending'],route['pending'])
  self.assertEqual(bridge.call_args.args[0],'manager-reconfigure')
