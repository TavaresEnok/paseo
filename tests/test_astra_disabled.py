import copy, json, unittest
from pathlib import Path
from orchestrator import policy_runtime as r
from orchestrator.model_limits import astra_allowed, role_summary

class AstraDisabled(unittest.TestCase):
 def test_all_other_quotas_exhausted_still_select_sol(self):
  limits=json.loads((Path(__file__).resolve().parents[1]/'config/model-limits.json').read_text())
  limits['supervision']['temporary_override']['enabled']=False
  now=10000
  state={'decisions':{'manager':{'model_key':'codex/gpt-6-astra'}}}
  for key in r.OBSERVATION_KEYS:
   if key!='codex':state=r.note_exhaustion(state,key,now,'quota exhausted')
  catalog=[{'provider':'codex','id':'gpt-6.1-sol','authenticated':True,'available':True,'quota':{'status':'available','observed_at':now,'windows':[{'remaining_fraction':1}]}}]
  d=r.evaluate('manager',catalog,limits,now=now,state=state)
  self.assertEqual(d['model_key'],'codex/gpt-6.1-sol')
  self.assertEqual(d['thinking_option'],'medium')
  self.assertFalse(d['wait'])
  self.assertFalse(astra_allowed('manager','gpt-6-astra','medium',limits))
  self.assertIn('Astra proibido',role_summary(limits))
  previous=copy.deepcopy(limits);previous['supervision']['temporary_override']['enabled']=True
  self.assertEqual(r.evaluate('manager',catalog,previous,now=now,state=state)['model_key'],'codex/gpt-6-astra')
