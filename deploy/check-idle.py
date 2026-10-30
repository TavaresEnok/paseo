#!/usr/bin/env python3
"""Fail closed before daemon maintenance. Does not trust one agents-list page."""
import json,sqlite3,subprocess,sys
from pathlib import Path
BASE=Path('/home/enok/srv_projetos');SOURCE=Path('/home/enok/.local/share/paseo-orchestrator')
def inspect():
 busy=[]
 with sqlite3.connect('file:'+str(BASE/'orchestration/state.sqlite3')+'?mode=ro',uri=True) as db:
  for task,state,agent,receipt in db.execute("SELECT id,state,agent_id,launch_request FROM tasks WHERE state IN ('running','launching','waiting_permission','validating') OR (launch_request IS NOT NULL AND state NOT IN ('done','blocked'))"):
   busy.append({'kind':'controller_task','task':task,'state':state,'agent':agent})
  names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  managers=[r[0] for r in db.execute('SELECT DISTINCT agent_id FROM manager_owners')] if 'manager_owners' in names else []
 for agent in managers:
  p=subprocess.run(['/home/enok/.local/share/node24/bin/node',str(SOURCE/'native/bridge.mjs')],input=json.dumps({'action':'agent','agentId':agent}),capture_output=True,text=True,timeout=20,check=True)
  v=json.loads(p.stdout);a=v.get('agent',v)
  if not a:continue
  if a.get('activeTurn') or a.get('pendingPermissions') or a.get('status') in ['running','starting','initializing','loading','waiting_permission']:
   busy.append({'kind':'manager','agent':agent,'state':a.get('status')})
 p=subprocess.run(['docker','ps','--filter','label=paseo.orchestrator.managed=true','--format','{{.ID}}'],capture_output=True,text=True,timeout=10,check=True)
 for container in p.stdout.split():busy.append({'kind':'worker_container','container':container})
 for path in (BASE/'orchestration/validation-operations').glob('*.request.json'):
  v=json.loads(path.read_text());result=path.with_name(path.name.replace('.request.json','.result.json'))
  if result.exists():continue
  try:alive=b'orchestrator.validation_jobs' in Path('/proc/'+str(v.get('pid'))+'/cmdline').read_bytes()
  except OSError:alive=False
  if alive:busy.append({'kind':'validation','context':v.get('context')})
 return {'safe_to_restart_daemon':not busy,'busy':busy}
if __name__=='__main__':
 try:r=inspect();print(json.dumps(r));sys.exit(0 if r['safe_to_restart_daemon'] else 1)
 except Exception as e:print(json.dumps({'safe_to_restart_daemon':False,'error':str(e)}));sys.exit(2)
