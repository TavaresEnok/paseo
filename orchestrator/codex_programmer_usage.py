"""Read-only ChatGPT quota for the isolated programmer account, never manager auth."""
import json,os,subprocess,time,selectors,hashlib,uuid
from pathlib import Path
HOME=Path('/home/enok/srv_projetos/runtime/isolated/codex-programmer/home')
CACHE=Path('/home/enok/srv_projetos/orchestration/evidence/codex-programmer-usage.json')
def evidence_entry(force=False):
 from .model_limits import load_limits
 effort=(load_limits().get("programmer_account") or {}).get("thinking","medium")
 if not force and CACHE.exists():
  v=json.loads(CACHE.read_text())
  v['safe_thinking_options']=[effort];v['label']='GPT-6.1 Terra '+('Alto' if effort=='high' else 'Médio')+' — conta programador'
  if time.time()-v.get('observed_at',0)<60:return v
 env=dict(os.environ,HOME=str(HOME),CODEX_HOME=str(HOME/'.codex'))
 for k in ('OPENAI_API_KEY','OPENAI_BASE_URL','CODEX_API_KEY'):env.pop(k,None)
 p=subprocess.Popen(['/home/enok/.local/share/node24/bin/codex','app-server'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
 deadline=time.monotonic()+15
 buffer=b''
 def rpc(i,m,params):
  nonlocal buffer
  p.stdin.write((json.dumps({'id':i,'method':m,'params':params})+'\n').encode());p.stdin.flush()
  poll=selectors.DefaultSelector();poll.register(p.stdout,selectors.EVENT_READ)
  try:
   while time.monotonic()<deadline:
    while b'\n' in buffer:
     line,buffer=buffer.split(b'\n',1)
     if not line:continue
     v=json.loads(line)
     if v.get('id')==i:
      if 'error' in v:raise RuntimeError('Codex quota read failed')
      return v.get('result',{})
    if not poll.select(min(1,max(0,deadline-time.monotonic()))):continue
    chunk=os.read(p.stdout.fileno(),65536)
    if not chunk:raise RuntimeError('Codex quota reader closed')
    buffer+=chunk
   raise RuntimeError('Codex quota read timed out')
  finally:poll.close()
 try:
  rpc(1,'initialize',{'clientInfo':{'name':'paseo_programmer_quota','version':'1.0'},'capabilities':{}})
  account=rpc(2,'account/read',{}).get('account') or {};rates=rpc(3,'account/rateLimits/read',{}).get('rateLimits') or {}
  if account.get('type')!='chatgpt':raise RuntimeError('Dedicated programmer account requires ChatGPT OAuth')
  windows=[]
  for name in ('primary','secondary'):
   w=rates.get(name)
   if w and isinstance(w.get('usedPercent'),(int,float)):windows.append({'id':name,'remaining_fraction':max(0,1-w['usedPercent']/100),'resets_at':w.get('resetsAt')})
  credits=rates.get('credits') or {}
  safe=credits.get('hasCredits') is False and credits.get('unlimited') is False
  status='exhausted' if any(w['remaining_fraction']<=0 for w in windows) else 'available' if windows else 'unknown'
  now=time.time();v={'id':'gpt-6.1-terra','provider':'codex-programmer','label':'GPT-6.1 Terra '+('Alto' if effort=='high' else 'Médio')+' — conta programador','available':True,'authenticated':True,'observed_at':now,'mode':'auto','safe_thinking_options':[effort],'roles':['programmer'],'preferred_specialties':['backend','coding','frontend','testing','debugging','advanced','architecture','utility','reasoning'],'account_hash':hashlib.sha256(account.get('email','').encode()).hexdigest(),'cost':{'kind':'subscription','verified':safe,'additional_cost':0 if safe else None,'source':'official Codex app-server ChatGPT OAuth; isolated programmer home; API keys stripped'},'quota':{'status':status,'observed_at':now,'source':'official codex app-server account/rateLimits/read','windows':windows},'restrictions':{'allowed':True,'notes':'Programmer only; Terra '+effort}}
  CACHE.parent.mkdir(parents=True,exist_ok=True);tmp=CACHE.with_name(CACHE.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(v));tmp.chmod(0o600);tmp.replace(CACHE);return v
 finally:
  p.terminate()
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.kill();p.wait()
if __name__=='__main__':print(json.dumps(evidence_entry()))
