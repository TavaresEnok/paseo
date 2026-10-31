import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from orchestrator import policy_integration as p,policy_runtime as r
class ModelQuotaSync(unittest.TestCase):
 def test_newer_partner_model_recovery_replaces_local_exhaustion(self):
  now=time.time();key=r.ANTIGRAVITY_SONNET_KEY
  local=r.note_exhaustion(None,key,now-60,'quota exhausted')
  remote=r._blank_state(None);r._accept(remote,key,'available',now,'official successful run')
  class Client:
   def observe(self,*_):return {'state':remote}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'orchestration').mkdir()
   with patch.object(p,'open_client',return_value=(Client(),p.CapacityUnavailable)),patch.object(p,'limits_file',return_value=root/'config/model-limits.json'):
    state=p.absorb_global(local,{'models':[]},{},now=now)
   self.assertEqual(state['observations'][key]['status'],'available')
   self.assertEqual(state['observations'][key]['observed_at'],now)
