import importlib.util,json,sqlite3,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class UsageSnapshot(unittest.TestCase):
 def test_cache_and_reasoning_are_not_double_counted(self):
  spec=importlib.util.spec_from_file_location('worker_comparison',ROOT/'deploy/worker-comparison.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);(home/'.codex').mkdir();rollout=home/'rollout.jsonl'
   usage={'input_tokens':10,'cached_input_tokens':6,'output_tokens':4,'reasoning_output_tokens':2,'total_tokens':14}
   rollout.write_text(json.dumps({'type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':usage}}})+'\n')
   with sqlite3.connect(home/'.codex/state_5.sqlite') as db:
    db.execute('CREATE TABLE threads(model TEXT,reasoning_effort TEXT,rollout_path TEXT,tokens_used INTEGER)')
    db.execute('INSERT INTO threads VALUES(?,?,?,?)',('gpt-6.1-terra','high',str(rollout),14))
   result=m.read_usage(home)['models']['gpt-6.1-terra/high']
   self.assertEqual(result['total_tokens'],14);self.assertEqual(result['cached_input_tokens'],6);self.assertEqual(result['reasoning_output_tokens'],2)
