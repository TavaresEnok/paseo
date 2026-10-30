#!/usr/bin/env python3
"""Read-only snapshots for worker quality/token comparisons. Never calls a model.

Capture before changing a phase; compare snapshots after comparable completed work.
Token counts include cached input; they are not subscription quota or API charges.
"""
import argparse,collections,datetime,json,sqlite3,time
from pathlib import Path
BASE=Path('/home/enok/srv_projetos')

def read_usage(home):
 path=home/'.codex/state_5.sqlite'
 totals={};missing=0
 if not path.exists():return {'models':{},'missing_rollouts':0}
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
  rows=db.execute('SELECT model,reasoning_effort,rollout_path,tokens_used FROM threads').fetchall()
 for model,effort,rollout,fallback in rows:
  key=str(model)+'/'+str(effort);bucket=totals.setdefault(key,collections.Counter());usage=None
  try:
   with open(rollout,'rb') as f:
    f.seek(0,2);size=f.tell();f.seek(max(0,size-262144));lines=f.read().splitlines()
   for line in reversed(lines):
    try:v=json.loads(line)
    except (ValueError,UnicodeError):continue
    p=v.get('payload') or {}
    if v.get('type')=='event_msg' and p.get('type')=='token_count':
     usage=(p.get('info') or {}).get('total_token_usage')
     if usage:break
  except OSError:pass
  bucket['sessions']+=1
  if usage:
   for name in ['input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens','total_tokens']:
    bucket[name]+=int(usage.get(name,0))
  else:bucket['tokens_without_breakdown']+=int(fallback or 0);missing+=1
 return {'models':dict(totals),'missing_rollouts':missing}

def capture():
 totals=collections.defaultdict(collections.Counter);seen=collections.defaultdict(set);rejected=collections.defaultdict(set);integrated=collections.defaultdict(set);selection={};active={}
 with sqlite3.connect('file:'+str(BASE/'orchestration/state.sqlite3')+'?mode=ro',uri=True) as db:
  max_seq=db.execute('SELECT coalesce(max(seq),0) FROM events').fetchone()[0]
  for seq,task,kind,raw in db.execute('SELECT seq,task_id,kind,data FROM events WHERE seq<=? ORDER BY seq',(max_seq,)):
   try:d=json.loads(raw or '{}')
   except ValueError:continue
   if kind=='model_selected' and d.get('role')=='programmer':
    x=d.get('selected') or {};selection[task]=(x.get('key'),x.get('thinking_option_id'))
   if kind=='agent_started' and d.get('phase')=='implement':
    model,effort=selection.get(task,(d.get('model'),'unknown'))
    key=str(model)+'/'+str(effort);active[task]=key;seen[key].add(task);totals[key]['implementation_starts']+=1
   key=active.get(task)
   if not key:continue
   if kind=='correction_requested' and not d.get('synthetic_fault_excluded_from_quality_history'):
    totals[key]['review_rejections']+=1;rejected[key].add(task)
   if kind=='task_integrated':totals[key]['integrations']+=1;integrated[key].add(task)
   if kind=='task_blocked' and not d.get('synthetic_fault_excluded_from_quality_history'):totals[key]['blocked_events_including_environment']+=1
 for key in totals:
  totals[key]['distinct_tasks']=len(seen[key]);totals[key]['tasks_with_review_rejection']=len(rejected[key]);totals[key]['integrated_without_rejection_for_this_variant']=len(integrated[key]-rejected[key])
 usage={}
 for account in ['codex-programmer','codex']:
  usage[account]=read_usage(BASE/'runtime/isolated'/account/'home')
 policy=json.loads((BASE/'config/model-limits.json').read_text()).get('programmer_account',{})
 try:
  observed=json.loads((BASE/'orchestration/evidence/codex-programmer-usage.json').read_text());quota=observed.get('quota',{})
 except (OSError,ValueError):quota={'status':'unknown'}
 return {'programmer_quota_snapshot':quota,'programmer_policy':{k:policy.get(k) for k in ['provider','model','thinking']},'at':time.time(),'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'event_seq':max_seq,'quality':dict(totals),'usage':usage,'notes':['Cumulative snapshots: subtract matching counters between phases.','Compare similar task complexity; inherited tasks and transport/auth/quota waits are not model-quality failures.','Cached input is included in input_tokens; reasoning_output_tokens is a subset of output_tokens.','Reviewer/manager original-account usage is grouped separately; no claim of quota savings from token counts.']}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('label');parser.add_argument('--output-dir',type=Path,default=BASE/'orchestration/evidence/worker-comparison');args=parser.parse_args()
 if not args.label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.label):parser.error('Use a simple phase label.')
 result=capture();args.output_dir.mkdir(parents=True,exist_ok=True)
 path=args.output_dir/(args.label+'.json')
 with path.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
 path.chmod(0o600);print(json.dumps({'snapshot':str(path),'at':result['timestamp_utc'],'event_seq':result['event_seq'],'quality':result['quality']},ensure_ascii=False))
if __name__=='__main__':main()
