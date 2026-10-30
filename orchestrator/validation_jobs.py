"""Durable background command execution; scheduler never waits for the runner."""
import hashlib,json,os,signal,subprocess,sys,time,threading
from pathlib import Path

CONTEXT=threading.local()

class Pending(Exception):pass

def atomic(path,data):
    tmp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    tmp.write_text(json.dumps(data));tmp.chmod(0o600);tmp.replace(path)

def alive(pid):
    try:
        os.kill(int(pid),0)
        return b'orchestrator.validation_jobs' in Path(f'/proc/{int(pid)}/cmdline').read_bytes()
    except (OSError,TypeError,ValueError):return False

def context_running(context):
    from . import core
    for path in (core.STATE/'validation-operations').glob('*.request.json'):
        try:
            value=json.loads(path.read_text())
            result=path.with_name(path.name.replace('.request.json','.result.json'))
            if value.get('context')==context and not result.exists() and alive(value.get('pid')):return True
        except (OSError,ValueError):continue
    return False

def acknowledge_context(context):
    """Retire receipts only AFTER the corresponding state transition commits."""
    from . import core
    for path in (core.STATE/'validation-operations').glob('*.request.json'):
        try:
            request=json.loads(path.read_text())
            if request.get('context')!=context:continue
            result=path.with_name(path.name.replace('.request.json','.result.json'))
            if not result.exists():continue
            value=json.loads(result.read_text())
            value['consumed']=True;value['acknowledged_at']=time.time();atomic(result,value)
        except (OSError,ValueError):
            # Database phase is authoritative after a crash/cleanup; don't undo it.
            continue

def pending_integrations(cwd,job_id):
    from . import core
    found=[]
    for path in (core.STATE/'validation-operations').glob('*.request.json'):
        request=json.loads(path.read_text())
        context=request.get('context') or {}
        if context.get('job')!=job_id or context.get('phase')!='integrate':continue
        if Path(request.get('cwd','')).resolve()!=Path(cwd).resolve():continue
        result=path.with_name(path.name.replace('.request.json','.result.json'))
        if result.exists() and json.loads(result.read_text()).get('consumed'):continue
        found.append((request.get('created',0),context.get('task')))
    return [task for _,task in sorted(found) if task]

def command(cwd,commands,timeout):
    from . import core
    from .operator_hold import require_running
    context=getattr(CONTEXT,'value',None)
    if not context:return core._run_test_commands(cwd,commands,timeout)
    require_running()
    root=core.STATE/'validation-operations';root.mkdir(exist_ok=True,mode=0o700)
    runner=core.runner_stamp(str(cwd),core.NODE)
    if runner is None:raise RuntimeError('Identidade do runner indisponível; validação preservada sem reutilização.')
    implementation=hashlib.sha256(Path(core.__file__).read_bytes()+Path(__file__).read_bytes()).hexdigest()
    identity=[context,str(cwd),commands,timeout,runner,implementation]
    key=hashlib.sha256(core.encoded(identity).encode()).hexdigest()
    request=root/(key+'.request.json');result=root/(key+'.result.json')
    if context_running(context):raise Pending('runner_running')
    digest=core.worktree_digest(cwd)
    previous=json.loads(request.read_text()) if request.exists() else {}
    if result.exists():
        value=json.loads(result.read_text())
        if not value.get('consumed') and not value.get('cancelled') and runner is not None and (value.get('input_digest')==digest or value.get('output_digest')==digest):
            if value.get('error'):raise RuntimeError(value['error'])
            return value['results']
    if previous and not result.exists() and alive(previous.get('pid')):raise Pending(key)
    # Bound runner memory independently from model workers.
    running=0
    for path in root.glob('*.request.json'):
        try:
            data=json.loads(path.read_text())
            if not path.with_name(path.name.replace('.request.json','.result.json')).exists() and alive(data.get('pid')):running+=1
        except (OSError,ValueError):continue
    if running>=2:raise Pending('runner_capacity')
    result.unlink(missing_ok=True)
    value={'context':context,'cwd':str(cwd),'commands':commands,'timeout':timeout,'input_digest':digest,'created':time.time()}
    atomic(request,value)
    env=dict(os.environ,PYTHONPATH=str(core.ROOT),PYTHONDONTWRITEBYTECODE='1',PASEO_VALIDATION_JOB=str(context.get('job') or ''))
    worker=subprocess.Popen([sys.executable,'-m','orchestrator.validation_jobs',str(request)],cwd=core.ROOT,env=env,
                            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    value['pid']=worker.pid;atomic(request,value)
    raise Pending(key)

def cancel(job_id=None):
    from . import core
    root=core.STATE/'validation-operations'
    for path in root.glob('*.request.json'):
        try:
            value=json.loads(path.read_text())
            if job_id and value.get('context',{}).get('job')!=job_id:continue
            if path.with_name(path.name.replace('.request.json','.result.json')).exists():continue
            pid=value.get('pid')
            # Verify process identity; stale PID reuse is never permission to kill.
            argv=Path(f'/proc/{pid}/cmdline').read_bytes()
            if b'orchestrator.validation_jobs' in argv and str(path).encode() in argv:
                os.killpg(int(pid),signal.SIGTERM)
        except (OSError,ValueError,TypeError):continue
    filters=['--filter','label=paseo.validation.managed=true']
    if job_id:filters+=['--filter','label=paseo.validation.job='+str(job_id)]
    found=subprocess.run(['docker','ps','-q',*filters],capture_output=True,text=True,timeout=10)
    if found.returncode==0:
        for container in found.stdout.split():subprocess.run(['docker','rm','-f',container],capture_output=True,timeout=15)

def main():
    from . import core
    from .operator_hold import require_running
    request=Path(sys.argv[1]);value=json.loads(request.read_text())
    result=request.with_name(request.name.replace('.request.json','.result.json'))
    def stop(*_):raise SystemExit('Validation cancelled by operator')
    signal.signal(signal.SIGTERM,stop)
    output={'input_digest':value['input_digest']}
    try:
        require_running()
        output['results']=core._run_test_commands(value['cwd'],value['commands'],value['timeout'])
        output['output_digest']=core.worktree_digest(value['cwd'])
    except (Exception,SystemExit) as error:
        output['error']=str(error);output['cancelled']=isinstance(error,SystemExit)
    output['finished']=time.time();atomic(result,output)

if __name__=='__main__':main()
