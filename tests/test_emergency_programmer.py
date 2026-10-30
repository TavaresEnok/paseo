import importlib.util,unittest
from orchestrator import policy_runtime as r
class Emergency(unittest.TestCase):
 def setUp(self):self.e={p:{'status':'exhausted'} for p in r.PROVIDERS};self.e['codex']['status']='available'
 def choose(self,prev=None,enabled=True):return r._select('programmer',self.e,prev,gemini_enabled=True,gemini2_enabled=True,gemini1_enabled=False,programmer_account=True,emergency_original=enabled)
 def test_last_resort_and_disabled(self):
  self.assertEqual(self.choose()['model_key'],'codex/gpt-6.1-terra');self.assertEqual(self.choose()['thinking_option'],'medium');self.assertTrue(self.choose(enabled=False)['wait'])
 def test_each_regular_returns(self):
  for p,key in [('grok',r.GROK_MEDIUM[0]),('codex-programmer',r.TERRA_MEDIUM[0]),('antigravity2',r.GEMINI2_HIGH[0])]:
   self.e[p]['status']='available';self.assertEqual(self.choose(r.EMERGENCY_TERRA[0])['model_key'],key);self.e[p]['status']='exhausted'
 def test_regular_stays_and_no_cota_waits(self):
  self.e['antigravity2']['status']='available';self.e['grok']['status']='available';self.assertEqual(self.choose(r.GEMINI2_HIGH[0])['model_key'],r.GEMINI2_HIGH[0])
  self.e={p:{'status':'exhausted'} for p in r.PROVIDERS};self.assertTrue(self.choose()['wait'])
 def test_unknown_is_not_recovery(self):
  self.e['grok']['status']='unknown';self.assertEqual(self.choose(r.EMERGENCY_TERRA[0])['model_key'],r.EMERGENCY_TERRA[0]);self.assertNotEqual(self.choose()['model_key'],r.EMERGENCY_TERRA[0])
if __name__=='__main__':unittest.main()
