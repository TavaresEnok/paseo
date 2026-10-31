import json,unittest
from pathlib import Path
from orchestrator import policy_runtime as r

class SonnetRouting(unittest.TestCase):
 def setUp(self):
  self.limits=json.loads((Path(__file__).resolve().parents[1]/'config/model-limits.json').read_text())
  self.now=10000
  self.catalog=[]
  for p in r.PROVIDERS:
   self.catalog.append(self.entry(p,'gemini-3.8-flash-high' if p=='antigravity2' else 'fixture',p=='codex'))
  self.catalog.append(self.entry('antigravity2','claude-sonnet-5-5-medium',True))
 def entry(self,p,m,available):
  return {'provider':p,'id':m,'authenticated':True,'available':True,'cost':{'verified':True,'kind':'subscription','additional_cost':0},'quota':{'status':'available' if available else 'exhausted','observed_at':self.now,'source':'official agy response' if p=='antigravity2' else 'fixture','windows':[{'remaining_fraction':1 if available else 0}]}}
 def test_separate_quota_and_emergency(self):
  d=r.evaluate('programmer',self.catalog,self.limits,now=self.now)
  self.assertEqual(d['model_key'],r.ANTIGRAVITY_SONNET_KEY)
  self.assertEqual(d['evidence']['antigravity2']['status'],'exhausted')
  self.assertFalse(d['gpt_only'])
  state=r.note_exhaustion(d['state'],r.ANTIGRAVITY_SONNET_KEY,self.now+1,'quota exhausted')
  d=r.evaluate('programmer',[],self.limits,now=self.now+2,state=state)
  self.assertEqual(d['model_key'],self.limits['programming']['emergency_original_account']['model'])
  self.assertTrue(d['gpt_only'])
 def test_return_from_emergency_positive_only_and_regular_sticky(self):
  state={'decisions':{'programmer':{'model_key':r.EMERGENCY_TERRA[0]}}}
  d=r.evaluate('programmer',self.catalog,self.limits,now=self.now,state=state)
  self.assertEqual(d['model_key'],r.ANTIGRAVITY_SONNET_KEY)
  self.catalog.append(self.entry('grok','grok-4.7',True))
  d=r.evaluate('programmer',self.catalog,self.limits,now=self.now,state=d['state'])
  self.assertEqual(d['model_key'],r.ANTIGRAVITY_SONNET_KEY)
 def test_quota_transport_distinction_and_independent_review(self):
  state=r.note_exhaustion({},r.ANTIGRAVITY_SONNET_KEY,self.now,'network timeout quota exhausted')
  self.assertNotIn(r.ANTIGRAVITY_SONNET_KEY,state['observations'])
  self.catalog.append(self.entry('claude','claude-sonnet-5-5',True))
  for task,effort in [({'difficulty':2},'medium'),({'allowed_files':['auth/token.py']},'high')]:
   d=r.evaluate('reviewer',self.catalog,self.limits,now=self.now,implementation_model=r.ANTIGRAVITY_SONNET_KEY,review_task=task)
   self.assertEqual(d['model_key'],r.SOL_MEDIUM[0]);self.assertEqual(d['thinking_option'],effort)
