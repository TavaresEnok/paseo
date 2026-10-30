import sqlite3,unittest
from orchestrator.supervision import recorded_fallback
from orchestrator.policy_integration import primary_return_effort

class ManagerRouteIdentity(unittest.TestCase):
 def test_staged_replacement_is_not_a_new_chat(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
  db.executescript("CREATE TABLE admission_tickets(agent_id TEXT,chat_id TEXT,role TEXT); CREATE TABLE supervisor_routes(fallback_id TEXT);")
  db.execute("INSERT INTO admission_tickets VALUES('replacement','public-chat','manager')")
  self.assertTrue(recorded_fallback(db,{'id':'replacement','labels':{}}))
  self.assertFalse(recorded_fallback(db,{'id':'public-chat','labels':{}}))
 def test_adaptive_high_original_can_return_from_medium_replacement(self):
  route={'active_id':'replacement','primary_id':'public-chat'}
  primary={'id':'public-chat','provider':'codex','model':'gpt-6.1-sol','thinkingOptionId':'high','status':'error'}
  selected={'provider':'codex','id':'gpt-6.1-sol','thinking_option_id':'medium'}
  settings={'primary_model':'codex/gpt-6.1-sol','adaptive_effort':{'enabled':True}}
  self.assertEqual(primary_return_effort(route,primary,selected,settings),'high')
  primary['activeTurn']={'id':'live'}
  self.assertIsNone(primary_return_effort(route,primary,selected,settings))
  primary.pop('activeTurn');selected['id']='gpt-6-astra'
  self.assertIsNone(primary_return_effort(route,primary,selected,settings))
 def test_temporary_label_is_never_discovered(self):
  self.assertTrue(recorded_fallback(None,{'id':'replacement','labels':{'flow.supervisor.role':'temporary'}}))
