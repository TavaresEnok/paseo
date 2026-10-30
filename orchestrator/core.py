from __future__ import annotations

import fnmatch
import fcntl
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import threading
import uuid

from .routing import select_for_task
from .resources import assess_resources, sample_resources
from .validation import (
    RUNNER_IMAGE, commands_cover, compact_results, enforce_task, integration_commands,
    policy_from_plan, proof_valid, reuse_decision, runner_stamp,
)

ROOT = Path('/home/enok/.local/share/paseo-orchestrator')
STATE = Path(os.environ.get('PASEO_FLOW_STATE', '/home/enok/srv_projetos/orchestration'))
NODE = '/home/enok/.local/share/node24/bin/node'
DEV = Path('/home/enok/srv_projetos/workspace')
MANAGER_ROOT = Path('/home/enok/Documentos/projetos')
WORKTREES = Path('/home/enok/srv_projetos/worktrees')
AUTONOMY_FILE = Path('/home/enok/srv_projetos/config/autonomy.json')
ENV = {**os.environ, 'PATH': '/home/enok/.local/share/node24/bin:/home/enok/.local/bin:' + os.environ.get('PATH', '')}
TERMINAL = {'done', 'blocked', 'canceled'}
INTEGRATION_DIRTY_PREFIX = 'Branch de integração contém alterações locais inesperadas.'
MUTATION_LOCK = threading.RLock()

class LaunchUncertain(RuntimeError):
    """The same durable native create request must be retried, never replaced."""

class ModelUnavailable(RuntimeError):
    """Wait for an authorized model without consuming an implementation retry."""

def serialized(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        with MUTATION_LOCK, (STATE/'mutation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try: return function(*args, **kwargs)
            finally: fcntl.flock(lock, fcntl.LOCK_UN)
    return guarded

def now(): return time.time()
def uid(): return uuid.uuid4().hex[:12]
def encoded(obj): return json.dumps(obj, ensure_ascii=False, sort_keys=True)
def decode(obj): return json.loads(obj) if isinstance(obj, str) else obj

def autonomy_policy():
    path=AUTONOMY_FILE
    return json.loads(path.read_text()) if path.exists() else {}

def bridge(action, timeout=90, **kwargs):
    from .supervision_io import CONTEXT,call
    if getattr(CONTEXT,'enabled',False) and action in {'send','archive','staged-launch','agent-create'}:
        return call(action,timeout,kwargs)
    return _bridge_sync(action,timeout,**kwargs)

def _bridge_sync(action, timeout=90, **kwargs):
    request = {'action': action, **kwargs}
    # Controller calls are top-level, not accidentally owned by the launching agent.
    env = {k: v for k, v in ENV.items() if k not in {'PASEO_AGENT_ID', 'PASEO_AGENT_CWD'}}
    result = subprocess.run([NODE, str(ROOT/'native/bridge.mjs')], input=encoded(request),
                            text=True, capture_output=True, timeout=timeout, env=env)
    try: data = json.loads(result.stdout)
    except ValueError: raise RuntimeError(f'Paseo bridge failed ({result.returncode}): {result.stderr[-1000:]}')
    if result.returncode or (isinstance(data, dict) and data.get('error')):
        raise RuntimeError(str(data.get('error', data)))
    return data

def git(path, *args):
    return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(path), *args],
                          capture_output=True, text=True, check=True, timeout=60).stdout.strip()

def exclude_local_control_files(repo):
    """Keep root-only control files out of Git without hiding tracked edits."""
    path=Path(git(repo,'rev-parse','--git-path','info/exclude'))
    if not path.is_absolute():path=Path(repo)/path
    if path.is_symlink():raise ValueError('Arquivo Git exclude não pode ser symlink.')
    patterns=['/.paseo-plan.json','/.paseo-context.md','/.paseo-result.json','/.paseo-review.json',
              '/.paseo-recover.json','/.paseo-recover-*.json']
    existing=path.read_text() if path.exists() else ''
    missing=[pattern for pattern in patterns if pattern not in existing.splitlines()]
    if missing:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a') as handle:handle.write('\n# Local orchestration control files\n'+'\n'.join(missing)+'\n')

def validate_integration_recovery(task,job):
    """Resume only the same clean, independently approved commit."""
    if git(job['repo'],'branch','--show-current')!=job['branch'] or not job['branch'].startswith('orchestration/'):
        raise ValueError('Branch de desenvolvimento do plano não está ativa.')
    exclude_local_control_files(job['repo'])
    dirty=git(job['repo'],'status','--porcelain')
    if dirty:raise ValueError(INTEGRATION_DIRTY_PREFIX+'\n'+dirty[:4000])
    result=decode(task['result']) or {};commit=task['commit_sha']
    if not commit or result.get('commit')!=commit or (result.get('review') or {}).get('decision')!='pass':
        raise ValueError('Recuperação requer o commit original e sua revisão independente aprovada.')
    if git(task['cwd'],'rev-parse','HEAD')!=commit or git(task['cwd'],'status','--porcelain'):
        raise ValueError('A worktree do commit revisado foi alterada; requer nova revisão.')
    checked_files(task)

def dev_path(value):
    path = Path(value).resolve()
    if path != MANAGER_ROOT.resolve() and not any(path.is_relative_to(root.resolve()) for root in (DEV, WORKTREES)):
        raise ValueError('Use um clone de desenvolvimento em workspace/ ou worktrees/, não produção.')
    if not path.is_dir(): raise ValueError('Diretório de desenvolvimento inexistente.')
    return path

def manager_cwd(value):
    """Directory a manager may use. Job and worker submission stay on dev_path.

    Without MANAGER_ROOT this is exactly dev_path. An installation that defines
    MANAGER_ROOT can also allow its subdirectories when autonomy explicitly sets
    unrestricted_tools or manager_host_access.
    """
    try:
        return dev_path(value)
    except ValueError as error:
        root = globals().get('MANAGER_ROOT')
        if root is None:
            raise
        path = Path(value).resolve()
        if not path.is_dir():
            raise ValueError('Diretório de gerência inexistente.') from error
        root = Path(root).resolve()
        policy = autonomy_policy()
        authorized = policy.get('unrestricted_tools') is True or policy.get('manager_host_access') is True
        if authorized and (path == root or root in path.parents):
            return path
        raise ValueError('Diretório de gerência não autorizado.') from error

def database():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(STATE/'state.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, objective TEXT NOT NULL, repo TEXT NOT NULL,
        branch TEXT NOT NULL, plan TEXT NOT NULL, plan_hash TEXT NOT NULL,
        state TEXT NOT NULL, supervisor_id TEXT, created REAL NOT NULL,
        approved REAL, approval TEXT, updated REAL NOT NULL, notified INTEGER DEFAULT 0);
      CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), task_key TEXT NOT NULL,
        spec TEXT NOT NULL, state TEXT NOT NULL, attempt INTEGER DEFAULT 0,
        phase TEXT DEFAULT 'implement', agent_id TEXT, workspace_id TEXT, cwd TEXT,
        branch TEXT, model TEXT, review_model TEXT, selection TEXT, started REAL,
        deadline REAL, error TEXT, result TEXT, commit_sha TEXT,
        updated REAL NOT NULL, UNIQUE(job_id,task_key));
      CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, job_id TEXT,
        task_id TEXT, kind TEXT NOT NULL, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT NOT NULL, task_id TEXT,
        success INTEGER NOT NULL, latency REAL, at REAL NOT NULL);
    ''')
    columns = {row['name'] for row in db.execute('PRAGMA table_info(tasks)')}
    for name, declaration in {
        'launch_request': 'TEXT', 'retry_at': 'REAL', 'base_commit': 'TEXT',
        'review_digest': 'TEXT', 'observed_running': 'INTEGER DEFAULT 0',
        'previous_agent_id': 'TEXT', 'launch_failures': 'INTEGER DEFAULT 0',
        'permission_wait_at': 'REAL', 'deadline_remaining': 'REAL', 'paused_state':'TEXT',
    }.items():
        if name not in columns: db.execute(f'ALTER TABLE tasks ADD COLUMN {name} {declaration}')
    # Failures caused by the test infrastructure stay recorded but do not rate the model.
    if 'excluded_reason' not in {row['name'] for row in db.execute('PRAGMA table_info(outcomes)')}:
        db.execute('ALTER TABLE outcomes ADD COLUMN excluded_reason TEXT')
    from .policy_integration import migrate_flow
    migrate_flow(db)
    db.commit()
    return db

def event(db, kind, data, job_id=None, task_id=None):
    db.execute('INSERT INTO events(at,job_id,task_id,kind,data) VALUES(?,?,?,?,?)',
               (now(), job_id, task_id, kind, encoded(data)))

def validate_plan(plan):
    if not isinstance(plan, dict) or not str(plan.get('objective', '')).strip():
        raise ValueError('Plano precisa de objective.')
    policy=policy_from_plan(plan)
    repo = dev_path(plan['repo'])
    if Path(git(repo, 'rev-parse', '--show-toplevel')).resolve() != repo:
        raise ValueError('repo deve ser a raiz de um repositório de desenvolvimento.')
    tasks = plan.get('tasks', [])
    if not isinstance(tasks,list) or not 1 <= len(tasks) <= 100 or any(not isinstance(t,dict) for t in tasks):
        raise ValueError('Plano deve conter de 1 a 100 tarefas válidas.')
    keys = [task.get('id') for task in tasks]
    if any(not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,50}', key) for key in keys) or len(set(keys)) != len(keys):
        raise ValueError('IDs de tarefas devem ser únicos e simples.')
    graph = {}
    for task in tasks:
        if not isinstance(task, dict): raise ValueError('Tarefa inválida.')
        if not task.get('objective') or not task.get('acceptance'):
            raise ValueError('Cada tarefa precisa de objetivo e critérios de aceite.')
        deps = task.get('depends_on', [])
        if not isinstance(deps, list): raise ValueError('depends_on deve ser lista.')
        if any(dep not in keys or dep == task['id'] for dep in deps): raise ValueError('Dependência inválida.')
        graph[task['id']] = deps
        if not isinstance(task.get('tests', []), list): raise ValueError('tests deve ser lista.')
        for command in task.get('tests', []):
            if not isinstance(command, list) or not command or any(not isinstance(v, str) for v in command):
                raise ValueError('Testes devem ser listas de argumentos, sem shell implícito.')
            if any('\x00' in value for value in command): raise ValueError('Argumento de teste inválido.')
        if not task.get('tests') and task.get('kind', 'code') == 'code':
            raise ValueError('Tarefa de código precisa de ao menos um teste.')
        if not 30 <= task.get('timeout_seconds', 900) <= 7200: raise ValueError('Prazo fora de 30..7200 segundos.')
        if not isinstance(task.get('allowed_files'), list) or not task['allowed_files']:
            raise ValueError('Declare allowed_files como lista para limitar alterações.')
        for pattern in task['allowed_files']:
            if not isinstance(pattern, str) or not pattern or pattern.startswith('/') or '..' in Path(pattern).parts or '.git' in Path(pattern).parts or '\x00' in pattern:
                raise ValueError('Escopo de arquivos inválido.')
        if type(task.get('max_attempts',3)) is not int or task.get('max_attempts',3) < 1:
            raise ValueError('max_attempts deve ser inteiro positivo.')
        if policy is not None: enforce_task(task)
    seen, stack = set(), set()
    def visit(key):
        if key in stack: raise ValueError('DAG contém ciclo.')
        if key in seen: return
        stack.add(key)
        for dep in graph[key]: visit(dep)
        stack.remove(key); seen.add(key)
    for key in keys: visit(key)
    return plan

@serialized
def submit(plan, supervisor_id=None):
    from .operator_hold import require_running
    require_running()
    validate_plan(plan)
    plan_hash = hashlib.sha256(encoded(plan).encode()).hexdigest()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute("SELECT id FROM jobs WHERE plan_hash=? AND state NOT IN ('canceled','blocked')", (plan_hash,)).fetchone()
        if prior: return {'job_id': prior['id'], 'duplicate': True}
        job_id = uid(); branch = 'orchestration/' + job_id
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (job_id, plan['objective'], str(dev_path(plan['repo'])), branch, encoded(plan), plan_hash,
                    'awaiting_approval', supervisor_id, now(), None, None, now(), 0))
        from .policy_integration import record_job_chat
        record_job_chat(db, job_id, supervisor_id or job_id)
        for spec in plan['tasks']:
            db.execute('INSERT INTO tasks(id,job_id,task_key,spec,state,updated) VALUES(?,?,?,?,?,?)',
                       (uid(), job_id, spec['id'], encoded(spec), 'queued', now()))
        event(db, 'plan_submitted', {'plan_hash': plan_hash, 'tasks': len(plan['tasks'])}, job_id)
    if autonomy_policy().get('auto_approve_development_plans') is True:
        result=_approve(job_id,standing=True)
        return {**result,'plan_hash':plan_hash}
    return {'job_id': job_id, 'plan_hash': plan_hash, 'state': 'awaiting_approval'}

def find_user_approval(timeline, message_id, job_id):
    # Only accept a real canonical user message, not assistant text or an agent envelope.
    if not isinstance(message_id,str) or not message_id: raise ValueError('message_id obrigatório.')
    if not isinstance(timeline,dict) or timeline.get('projection') not in {'canonical','projected'}:
        raise ValueError('Aprovação requer timeline nativa do Paseo.')
    # Only canonical top-level rows count. Never traverse tool results or quoted
    # assistant JSON, which can contain fabricated user_message objects.
    for entry in timeline.get('entries',[]):
        item = entry.get('item',{})
        if item.get('type') != 'user_message': continue
        if message_id not in {item.get('messageId'), item.get('id'), item.get('clientMessageId')}: continue
        text = str(item.get('text', ''))
        if item.get('source') or item.get('sender') or item.get('agentMessage'): continue
        if any(marker in text.lower() for marker in ['<agent', '<paseo-system', 'agent-message', 'from_agent', 'senderagentid']): continue
        if re.fullmatch(r'(aprovo|aprovado|approve|approved)\s+'+re.escape(job_id)+r'[.!]?', text.strip(), re.I):
            return {'message_id': message_id, 'job_id': job_id, 'source': 'native_user_message'}
    raise ValueError(f'Aprovação não encontrada. Na conversa, escreva: Aprovo {job_id}.')

@serialized
def approve(job_id, message_id=None, reason=None, caller_agent_id=None, standing=False):
    return _approve(job_id,message_id,reason,caller_agent_id,standing)

def _approve(job_id, message_id=None, reason=None, caller_agent_id=None, standing=False):
    with database() as db:
        job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not job: raise ValueError('Plano inexistente.')
        if job['state'] != 'awaiting_approval': return {'job_id': job_id, 'state': job['state']}
        caller = caller_agent_id or os.environ.get('PASEO_AGENT_ID')
        if standing:
            policy=autonomy_policy()
            if policy.get('auto_approve_development_plans') is not True:raise ValueError('Autonomia de desenvolvimento não autorizada.')
            evidence={'source':'standing_user_authorization','reason':policy.get('authorization'),'scope':'development_only'}
        elif caller:
            if caller != job['supervisor_id'] or not message_id: raise ValueError('Agente deve fornecer aprovação humana na conversa do supervisor.')
            evidence = find_user_approval(bridge('timeline', agentId=caller, options={'limit':100,'direction':'tail','projection':'canonical'}), message_id, job_id)
        else:
            if not reason: raise ValueError('Informe o motivo/autorização humana em --reason.')
            evidence = {'source':'human_local_cli', 'reason': reason}
        exclude_local_control_files(job['repo'])
        if git(job['repo'], 'status', '--porcelain'): raise ValueError('Clone de integração deve estar limpo antes de iniciar.')
        existing = git(job['repo'], 'branch', '--list', job['branch']).strip()
        if existing:
            if git(job['repo'],'branch','--show-current') != job['branch']:
                raise ValueError('Branch de integração já existe fora do checkout esperado; revise antes de retomar.')
        else: git(job['repo'], 'switch', '-c', job['branch'])
        db.execute("UPDATE jobs SET state='running',approved=?,approval=?,updated=? WHERE id=?",
                   (now(), encoded(evidence), now(), job_id))
        event(db, 'plan_approved', {'plan_hash': job['plan_hash'], **evidence}, job_id)
    return {'job_id':job_id,'state':'running'}

@serialized
def pause(job_id=None):
    """Persist the stop before contacting providers, so no new work is admitted."""
    if job_id is None:
        from .operator_hold import set_hold
        set_hold('Pausa global explícita do usuário')
    return _pause(job_id)

@serialized
def _pause(job_id=None):
    with database() as db:
        jobs=db.execute("SELECT id FROM jobs WHERE state IN ('running','blocked')"+(' AND id=?' if job_id else ''),
                        (job_id,) if job_id else ()).fetchall()
        agents=[]
        for row in jobs:
            agents.extend(r['agent_id'] for r in db.execute("SELECT agent_id FROM tasks WHERE job_id=? AND state IN ('running','launching','waiting_permission','validating') AND agent_id IS NOT NULL",(row['id'],)))
            db.execute("UPDATE jobs SET state='paused',updated=? WHERE id=?",(now(),row['id']))
            db.execute("UPDATE tasks SET paused_state=state,state='paused',updated=? WHERE job_id=? AND state IN ('running','launching','waiting_permission','validating','integrating')",(now(),row['id']))
            event(db,'job_paused',{'source':'operator_or_supervisor'},row['id'])
    from .validation_jobs import cancel
    cancel(job_id)
    errors=[]
    for agent_id in agents:
        try:bridge('stop',agentId=agent_id)
        except Exception as exc:errors.append({'agent_id':agent_id,'error':str(exc)[:500]})
    return {'paused':[row['id'] for row in jobs],'stop_errors':errors}

def _snapshot_busy(snapshot):
    if not isinstance(snapshot,dict):return False
    status=snapshot.get('status') or snapshot.get('lifecycle')
    return bool(snapshot.get('activeTurn') or snapshot.get('pendingPermissions') or status in {'running','starting','loading','initializing','waiting_permission','awaiting_permission'})

@serialized
def resume(job_id, reason, caller_agent_id=None):
    """Continue one approved paused plan. Explicit, same worktrees, no second executor."""
    if not isinstance(reason,str) or not reason.strip():raise ValueError('Informe o motivo da retomada em reason.')
    reason=reason.strip()
    with database() as db:
        job=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not job:raise ValueError('Plano inexistente.')
        caller=caller_agent_id or os.environ.get('PASEO_AGENT_ID')
        if caller:
            if caller!=job['supervisor_id']:raise ValueError('Somente o supervisor deste plano pode retomá-lo.')
            if not native_snapshot(caller):raise ValueError('Supervisor inexistente.')
        from .operator_hold import require_running
        require_running()
        if job['state']=='canceled':raise ValueError('Plano cancelado não pode ser retomado.')
        if job['state']=='running':return {'job_id':job_id,'state':'running','idempotent':True}
        if job['state']!='paused' or not job['approved']:raise ValueError('Retomada exige plano aprovado e paused.')
        if git(job['repo'],'branch','--show-current')!=job['branch'] or not job['branch'].startswith('orchestration/'):
            raise ValueError('Branch de desenvolvimento do plano não está ativa.')
        if db.execute("SELECT 1 FROM jobs WHERE repo=? AND id<>? AND state='running'",(job['repo'],job_id)).fetchone():
            raise ValueError('Outro plano está executando neste clone.')
        tasks=db.execute('SELECT * FROM tasks WHERE job_id=? ORDER BY rowid',(job_id,)).fetchall()
        for task in tasks:
            if task['state']=='paused' and task['agent_id']:
                try:snapshot=native_snapshot(task['agent_id'])
                except (RuntimeError,subprocess.SubprocessError) as exc:
                    raise ValueError('Não foi possível confirmar que o agente anterior está livre.') from exc
                if _snapshot_busy(snapshot):raise ValueError('Agente anterior ainda está ocupado; retomada não duplica o executor.')
        plan=decode(job['plan']);previous_hash=job['plan_hash'];extended=[];receipts=[];requeued=[]
        for task in tasks:
            if task['state']!='paused':continue
            if task['paused_state']=='validating':
                db.execute("UPDATE tasks SET state='validating',paused_state=NULL,deadline=NULL,updated=? WHERE id=?",(now(),task['id']))
                requeued.append(task['task_key']);continue
            if task['phase']=='integrate' and task['commit_sha']:
                db.execute("UPDATE tasks SET state='integrating',updated=? WHERE id=?",(now(),task['id']))
                requeued.append(task['task_key']);continue
            if task['launch_request']:
                db.execute("UPDATE tasks SET state='queued',updated=? WHERE id=?",(now(),task['id']))
                receipts.append(task['task_key']);requeued.append(task['task_key']);continue
            if task['agent_id'] and not task['error']:
                from .worker_lifecycle import retire
                if not retire(db,task):raise ValueError('Encerramento anterior ainda sem confirmação; preservado para reconciliação.')
                db.execute("UPDATE tasks SET state='queued',previous_agent_id=agent_id,agent_id=NULL,error='maintenance_resume:interrupted without task failure',retry_at=NULL,updated=? WHERE id=?",(now(),task['id']))
                requeued.append(task['task_key']);continue
            if task['agent_id']:
                from .worker_lifecycle import retire
                if not retire(db,task):raise ValueError('Encerramento anterior ainda não confirmado.')
            spec=decode(task['spec']);max_attempts=int(spec.get('max_attempts',3))
            if task['attempt']>=max_attempts:
                spec['max_attempts']=task['attempt']+1
                for item in plan['tasks']:
                    if item.get('id')==task['task_key']:item['max_attempts']=spec['max_attempts']
                extended.append({'task_key':task['task_key'],'attempt':task['attempt'],'max_attempts':spec['max_attempts']})
                db.execute('UPDATE tasks SET spec=?,updated=? WHERE id=?',(encoded(spec),now(),task['id']))
            db.execute("UPDATE tasks SET state='queued',agent_id=NULL,retry_at=NULL,updated=? WHERE id=?",(now(),task['id']))
            requeued.append(task['task_key'])
        if extended:
            validate_plan(plan)
            plan_hash=hashlib.sha256(encoded(plan).encode()).hexdigest()
            db.execute('UPDATE jobs SET plan=?,plan_hash=? WHERE id=?',(encoded(plan),plan_hash,job_id))
        else:plan_hash=previous_hash
        db.execute("UPDATE jobs SET state='running',notified=0,updated=? WHERE id=?",(now(),job_id))
        event(db,'job_resumed',{'reason':reason,'plan_hash':plan_hash,'previous_plan_hash':previous_hash,'supervisor_id':caller,
            'explicit':True,'preserve_completed_tasks':True,'attempt_extensions':extended,'receipts_preserved':receipts},job_id)
    return {'job_id':job_id,'state':'running','plan_hash':plan_hash,'resumed_tasks':requeued,'receipts_preserved':receipts,'attempt_extensions':extended}

def status(job_id=None):
    with database() as db:
        jobs = [dict(row) for row in db.execute('SELECT * FROM jobs' + (' WHERE id=?' if job_id else '') + ' ORDER BY created DESC', (job_id,) if job_id else ())]
        for job in jobs:
            job['plan'] = decode(job['plan'])
            job['tasks'] = [dict(t) for t in db.execute('SELECT * FROM tasks WHERE job_id=? ORDER BY rowid', (job['id'],))]
            for task in job['tasks']:
                for field in ['spec','selection','result']:
                    if task[field]: task[field] = decode(task[field])
        return jobs

@serialized
def recover(job_id, reason, revised_task=None, caller_agent_id=None):
    """Repair one approved job in place, retaining attempts, worktrees and audit."""
    if not isinstance(reason,str) or not reason.strip():raise ValueError('Explique a causa e a correção em reason.')
    with database() as db:
        job=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not job or job['state'] not in {'running','blocked'}:raise ValueError('Recuperação exige plano running ou blocked; planos pausados não são retomados.')
        if not job['approved']:raise ValueError('Plano ainda não aprovado.')
        caller=caller_agent_id or os.environ.get('PASEO_AGENT_ID')
        if caller:
            if caller!=job['supervisor_id']:raise ValueError('Somente o supervisor deste plano pode recuperá-lo.')
            if not autonomy_policy().get('unattended_development'):raise ValueError('Recuperação pelo supervisor requer autonomia autorizada.')
            snapshot=native_snapshot(caller)
            if not snapshot:raise ValueError('Supervisor inexistente.')
            manager_cwd(snapshot['cwd'])
        if git(job['repo'],'branch','--show-current')!=job['branch'] or not job['branch'].startswith('orchestration/'):
            raise ValueError('Branch de desenvolvimento do plano não está ativa.')
        if db.execute("SELECT 1 FROM jobs WHERE repo=? AND id<>? AND state='running'",(job['repo'],job_id)).fetchone():
            raise ValueError('Outro plano está executando neste clone.')
        previous_hash=job['plan_hash'];plan=decode(job['plan']);task_id=None
        if revised_task is not None:
            if not isinstance(revised_task,dict):raise ValueError('revised_task deve ser um objeto de tarefa completo.')
            task=db.execute('SELECT * FROM tasks WHERE job_id=? AND task_key=?',(job_id,revised_task.get('id'))).fetchone()
            if not task or task['state'] not in {'blocked','queued'} or task['agent_id'] or task['launch_request']:
                raise ValueError('Somente tarefa existente, parada e não concluída pode ser corrigida.')
            if task['phase']!='implement':raise ValueError('Não altere um contrato durante revisão ou integração.')
            original=decode(task['spec'])
            mutable={'objective','allowed_files','acceptance','tests','max_attempts'}
            if any(original.get(key)!=revised_task.get(key) for key in set(original)|set(revised_task) if key not in mutable):
                raise ValueError('Recuperação não muda identidade, dependências, modelos ou modo de execução.')
            if not set(map(encoded,original.get('tests',[]))).issubset(map(encoded,revised_task.get('tests',[]))):
                raise ValueError('Recuperação não pode remover testes existentes.')
            if not set(original.get('acceptance',[])).issubset(revised_task.get('acceptance',[])):
                raise ValueError('Recuperação não pode remover critérios existentes.')
            if task['attempt']>=revised_task.get('max_attempts',3):raise ValueError('Tentativas esgotadas; declare uma nova tentativa com justificativa da correção.')
            if revised_task.get('max_attempts',3)>max(original.get('max_attempts',3),task['attempt'])+1:raise ValueError('Recuperação amplia max_attempts uma tentativa por decisão justificada.')
            plan['tasks']=[revised_task if spec['id']==task['task_key'] else spec for spec in plan['tasks']]
            validate_plan(plan)
            if any(dep['state']=='done' and task['task_key'] in decode(dep['spec']).get('depends_on',[]) for dep in db.execute('SELECT * FROM tasks WHERE job_id=?',(job_id,))):
                raise ValueError('Uma tarefa concluída já depende deste contrato.')
            task_id=task['id']
            event(db,'task_contract_revised',{'reason':reason,'before':original,'after':revised_task,'previous_error':task['error'],'attempts_preserved':task['attempt']},job_id,task_id)
            db.execute("UPDATE tasks SET spec=?,state='queued',retry_at=NULL,updated=? WHERE id=?",(encoded(revised_task),now(),task_id))
        recovered_integrations=[]
        if revised_task is None:
            pending=db.execute("SELECT * FROM tasks WHERE job_id=? AND state='blocked' AND phase='integrate'",(job_id,)).fetchall()
            for task in pending:validate_integration_recovery(task,job)
            for task in pending:
                db.execute("UPDATE tasks SET state='integrating',error=NULL,updated=? WHERE id=?",(now(),task['id']))
                event(db,'integration_recovered',{'commit':task['commit_sha'],'reason':reason,'previous_error':task['error'],'attempts_preserved':task['attempt']},job_id,task['id'])
                recovered_integrations.append(task['task_key'])
        plan_hash=hashlib.sha256(encoded(plan).encode()).hexdigest()
        db.execute("UPDATE jobs SET state='running',plan=?,plan_hash=?,notified=0,updated=? WHERE id=?",(encoded(plan),plan_hash,now(),job_id))
        event(db,'job_recovered',{'reason':reason,'previous_plan_hash':previous_hash,'plan_hash':plan_hash,'supervisor_id':caller,'preserve_completed_tasks':True},job_id,task_id)
    return {'job_id':job_id,'state':'running','revised_task':revised_task.get('id') if revised_task else None,'integrations_recovered':recovered_integrations,'plan_hash':plan_hash}

def history(db):
    return {r['model']:{'successes':r['successes'],'failures':r['failures'], 'latency_seconds':r['latency_seconds'], 'observed_at':r['observed_at']}
            for r in db.execute('SELECT model,sum(success) successes,sum(1-success) failures,avg(latency) latency_seconds,max(at) observed_at FROM outcomes WHERE excluded_reason IS NULL GROUP BY model')}

def select(db, task, active):
    catalog = json.loads((STATE/'catalog.json').read_text())
    spec = decode(task['spec'])
    query = {**spec, 'specialty': 'review' if task['phase']=='review' else spec.get('specialty','coding')}
    query.pop('reviewer_route', None)
    if task['phase']=='review':query['implementation_model']=task.get('model')
    excluded = list(spec.get('excluded_models', []))
    # Reviews use a separate native agent/session. The configured reviewer and
    # its quota substitute may match an implementation model without an impossible allowlist.
    from .model_limits import load_limits
    review_policy=load_limits().get('review') or {}
    protected_reviewers={review_policy.get('model'), review_policy.get('fallback_model')} - {None}
    if task['phase']=='review' and task['model'] and task['model'] not in protected_reviewers: excluded.append(task['model'])
    if task['phase']=='review':
        from . import reviewer_routes
        reviewer_routes.consider_return(db, catalog)
        route=reviewer_routes.current_route(db)
        # Only the reviewer already in this turn keeps its role. A queued review
        # may return to the primary while that substitute finishes elsewhere.
        if route and task.get('state') in {'running','launching','waiting_permission'}:
            route={**route, 'hold_return': True}
        if route:
            query['reviewer_route']=route
    # Programming corrections stay with Grok; retries cannot switch providers.
    fixed_programmer=load_limits().get('programming',{}).get('model')
    if task['phase']=='implement' and task['attempt'] >= 2 and task['model'] and task['model'] not in {'codex/gpt-6.1-sol',fixed_programmer}: excluded.append(task['model'])
    query['excluded_models'] = excluded
    from .policy_integration import attach_policy_state, policy_enabled, store_policy_state
    if policy_enabled():
        query = attach_policy_state(db, task, query, catalog)
    result = select_for_task(catalog, query, history(db), active_models=active, attempt=task['attempt'], previous_model=task['model'], phase=task['phase'])
    if policy_enabled():
        store_policy_state(db, task, result)
    if not result['selected']: raise ModelUnavailable('Nenhum modelo permitido disponível: ' + encoded(result['rejected']))
    event(db, 'model_selected', result, task['job_id'], task['id'])
    return result

def extract_workspace(response):
    if 'workspace' in response: response = response['workspace']
    return response.get('workspaceId') or response.get('id'), response.get('cwd') or response.get('workspaceDirectory') or response.get('path')

def extract_agent(response):
    if 'agent' in response: response = response['agent']
    return response.get('id') or response.get('agentId')

def _plan_policy(job):
    if not hasattr(job, 'keys') or 'plan' not in job.keys(): return None
    raw=job['plan']
    if not raw: return None
    plan=decode(raw) if isinstance(raw, str) else raw
    if not isinstance(plan, dict): return None
    return policy_from_plan(plan)

def prompt_for(job, task, spec):
    common = f'''Trabalhe SOMENTE nesta worktree de desenvolvimento: {task['cwd']}.
Você é executor desta tarefa delimitada, não o gerente. O contrato já foi definido: leia os poucos padrões necessários em lote e avance à implementação; evite reler arquivos e fazer descoberta geral indefinidamente.
Plano aprovado: {job['objective']}\nTarefa: {spec['objective']}\nCritérios: {encoded(spec['acceptance'])}
Arquivos autorizados: {encoded(spec['allowed_files'])}\nTestes obrigatórios: {encoded(spec['tests'])}
Não faça deploy, push, merge, acesso a produção/credenciais, instalação de serviços ou uso de API paga.
Não crie agentes fora do controlador. Não faça commit: o controlador verifica e integra numa branch de desenvolvimento.
Não altere testes existentes para mascarar falhas. Você pode ler arquivos relevantes e executar os testes.
Grave código e arquivos de resultado usando apply_patch/Write. Para os metadados, evite Python -c, redirecionamentos e scripts shell: o controlador valida os caminhos de patches diretamente.
'''
    if autonomy_policy().get('unrestricted_tools') is True:
        common=common.replace('Não faça deploy, push, merge, acesso a produção/credenciais, instalação de serviços ou uso de API paga.', 'Ferramentas e comandos estão autorizados pelo usuário; preserve a política de modelos e assinatura sem custos adicionais.')
        common=common.replace('Grave código e arquivos de resultado usando apply_patch/Write. Para os metadados, evite Python -c, redirecionamentos e scripts shell: o controlador valida os caminhos de patches diretamente.', 'Use a ferramenta adequada para gravar código e metadados de resultado, sem pedir liberação de comandos.')
    policy=_plan_policy(job)
    if task['phase']=='review':
        if policy is not None:
            return common + '''Faça revisão independente das alterações presentes. Não modifique o código.
Escreva .paseo-review.json com {"decision":"pass" ou "fail","issues":[],"summary":"..."}.
Reprove problemas reais de correção ou ausência de requisitos. Leia o código e os resultados de checks já registrados em .paseo-result.json e pelo controlador.
Não repita a bateria essencial por padrão. Execute verificação adicional somente com justificativa técnica: falha, mudança relevante de código, risco não coberto pelos checks essenciais ou evidência ausente.
Resultados curtos: comando, status e resumo. Log grande somente em falha e no trecho relevante.
Não alegue economia percentual de tokens.
'''
        return common + '''Faça revisão independente das alterações presentes. Não modifique o código.
Escreva .paseo-review.json com {"decision":"pass" ou "fail","issues":[],"summary":"..."}.
Reprove problemas reais de correção ou ausência de requisitos. Leia o código e execute testes relevantes.'''
    previous = task['error'] or ''
    if policy is not None:
        return common + f'''Implemente a tarefa e corrija quaisquer falhas. Modo proporcional: implemente primeiro o bloco funcional completo.
Ao final do bloco, faça uma única rodada dos checks essenciais listados em Testes obrigatórios.
Repita esses checks somente se um falhar ou se o código mudar de forma relevante depois dessa rodada.
Resultados curtos: comando, status e resumo. Log grande somente em falha e no trecho relevante.
Não alegue economia percentual de tokens. O controlador registra a contagem de checks executados e reutilizados.
Contexto de tentativa anterior: {previous}
Ao terminar, escreva .paseo-result.json com {{"status":"completed" ou "blocked","summary":"...","files":[],"tests":[],"problems":[]}}.
Se encontrar impedimento real, registre-o. Não declare sucesso sem implementar.
'''
    return common + f'''Implemente a tarefa e corrija quaisquer falhas. Contexto de tentativa anterior: {previous}
Ao terminar, escreva .paseo-result.json com {{"status":"completed" ou "blocked","summary":"...","files":[],"tests":[],"problems":[]}}.
Se encontrar impedimento real, registre-o. Não declare sucesso sem implementar.
'''

def launch(db, task, job, active):
    from .operator_hold import require_running
    require_running()
    task=dict(task); spec=decode(task['spec'])
    action='agent-create'
    if task.get('launch_request'):
        options=decode(task['launch_request'])
        if options.get('callerAgentId') is None:
            options.pop('callerAgentId', None)
        if options.get('provider')=='grok':
            options.pop('modeId',None) # CLI controls unattended mode; ACP advertises no modes.
        if options.get('admissionTicket'):
            action='staged-launch'
        selection=decode(task['selection']); model=selection['selected']
        attempt=task['attempt']
    else:
        selection=select(db,task,active); model=selection['selected']
        if not task['workspace_id']:
            branch=f"task/{job['id']}/{task['task_key']}"
            workspace=bridge('workspace-create',options={'idempotencyKey':f"flow-workspace-{task['id']}",
                'background':autonomy_policy().get('hide_worker_workspaces',False),
                'source':{'kind':'worktree','cwd':job['repo'],'action':'branch-off','branchName':branch,'baseBranch':'refs/heads/'+job['branch']}})
            workspace_id,cwd=extract_workspace(workspace)
            if not workspace_id or not cwd: raise RuntimeError('Workspace response missing ID/path: '+encoded(workspace))
            dev_path(cwd)
            from .projects import prepare_dependency_cache
            cached=prepare_dependency_cache(job['repo'],cwd)
            if cached:event(db,'dependency_cache_prepared',{'paths':cached},job['id'],task['id'])
            task.update(workspace_id=workspace_id,cwd=cwd,branch=branch)
            db.execute('UPDATE tasks SET workspace_id=?,cwd=?,branch=?,base_commit=? WHERE id=?',
                       (workspace_id,cwd,branch,git(cwd,'rev-parse','HEAD'),task['id']))
            db.commit()
        # A review launch, including a quota substitute, keeps the implementation
        # artifact and digest. Only a stale review decision is cleared.
        preserve_quota=str(task.get('error') or '').startswith(('programmer_quota','maintenance_resume'))
        for name in ['.paseo-result.json','.paseo-review.json']:
            if task['phase']=='review' and name=='.paseo-result.json':
                continue
            if preserve_quota and name=='.paseo-result.json':
                continue
            (Path(task['cwd'])/name).unlink(missing_ok=True)
        attempt=task['attempt'] + (task['phase']=='implement' and not preserve_quota)
        review_generation=0
        if task['phase']=='review':
            from .reviewer_routes import current_route
            review_generation=int((current_route(db) or {}).get('generation') or 0)
        prompt=prompt_for(job,task,spec)
        options={'provider':model['provider'],'model':model['id'],
            'thinkingOptionId':model.get('thinking_option_id'),
            'modeId':model.get('mode') or {'claude':'acceptEdits','codex-programmer':'auto','codex':'auto','opencode':'build','grok':'bypassPermissions','antigravity':'full-access','antigravity2':'full-access','antigravity3':'full-access'}[model['provider']],
            'workspaceId':task['workspace_id'],'cwd':task['cwd'],'initialPrompt':prompt,
            'title':f"[{job['id']}/{task['task_key']}] {task['phase']}",
            'idempotencyKey':f"flow-{task['id']}-{task['phase']}-{attempt}"+(f"-{spec['launch_namespace']}" if spec.get('launch_namespace') else '')+(f"-r{review_generation}" if review_generation else ''),
            'labels':{'flow.job':job['id'],'flow.task':task['id'],'flow.phase':task['phase']}}
        if job['supervisor_id']:
            options['callerAgentId']=job['supervisor_id']
        if model['provider']=='grok':
            options.pop('modeId',None)
        from .policy_integration import policy_enabled, prepare_native_launch
        if policy_enabled():
            action, options = prepare_native_launch(db, task, job, selection, options)
        # The exact request, attempt and selected model are committed BEFORE the
        # external side effect. Recovery must never clear output or choose again.
        task['started']=now();task['deadline']=task['started']+spec.get('timeout_seconds',900)
        db.execute("UPDATE tasks SET state='launching',attempt=?,selection=?,launch_request=?,retry_at=?,started=?,deadline=?,launch_failures=0,permission_wait_at=NULL,deadline_remaining=NULL,updated=? WHERE id=?",
                   (attempt,encoded(selection),encoded(options),now()+15,task['started'],task['deadline'],now(),task['id']))
        db.commit()
    try:
        response=bridge(action,options=options)
        agent_id=extract_agent(response)
        if not agent_id: raise RuntimeError('Agent response missing ID')
    except Exception as error:
        from .worker_lifecycle import launch_quota
        if launch_quota(db,task,options,selection,str(error)):return
        from .worker_lifecycle import launch_rejected
        if launch_rejected(db,task,options,str(error)):return
        if task['phase']=='review':
            from .reviewer_routes import note_session_quota, quota_failure_reason
            view=dict(task)
            view['selection']=encoded(selection)
            view['review_model']=model['key']
            evidence=quota_failure_reason(view, {'lastError': str(error)})
            if evidence and note_session_quota(db, view, str(error), evidence):
                db.commit()
                return
        db.execute("UPDATE tasks SET state='launching',retry_at=?,launch_failures=launch_failures+1,error=?,updated=? WHERE id=?",
                   (now()+min(300,15*max(1,int(task.get('launch_failures') or 0)+1)),str(error)[-2000:],now(),task['id']))
        if int(task.get('launch_failures') or 0)==2:
            event(db,'launch_requires_attention',{'error':str(error)[-1200:],'preserve_receipt':True},job['id'],task['id'])
            db.execute('UPDATE jobs SET notified=0 WHERE id=?',(job['id'],))
        event(db,'launch_receipt_pending',{'idempotency_key':options['idempotencyKey'],'error':str(error)[-2000:]},job['id'],task['id'])
        from .policy_integration import mark_uncertain, policy_enabled
        if policy_enabled():
            mark_uncertain(db, task)
        db.commit()
        raise LaunchUncertain(str(error)) from error
    column='review_model' if task['phase']=='review' else 'model'
    db.execute(f"UPDATE tasks SET state='running',attempt=?,agent_id=?,{column}=?,started=?,deadline=?,observed_running=0,launch_request=NULL,retry_at=NULL,error=NULL,updated=? WHERE id=?",
               (attempt,agent_id,model['key'],task['started'],task['deadline'],now(),task['id']))
    event(db,'agent_started',{'agent_id':agent_id,'model':model['key'],'phase':task['phase'],'attempt':attempt},job['id'],task['id'])
    from .policy_integration import bind_launched, policy_enabled
    if policy_enabled():
        bind_launched(db, task, agent_id)
    db.commit()

_SENSITIVE_GIT_PARTS = {
    'docker.sock', '.docker', 'credentials', '.credentials', '.credentials.json',
    '.git-credentials', '.netrc', '.npmrc', '.pypirc', 'id_rsa', 'id_dsa', 'id_ed25519',
    'authorized_keys', '.aws', '.ssh', '.gnupg', '.kube', '.gitconfig',
}

def _under_dev_roots(path):
    resolved = Path(os.path.realpath(path))
    return any(resolved == Path(root).resolve() or resolved.is_relative_to(Path(root).resolve()) for root in (DEV, WORKTREES))

def _in_production(path):
    resolved = Path(os.path.realpath(path))
    root = Path(MANAGER_ROOT).resolve()
    return resolved == root or root in resolved.parents

def _sensitive_git_path(path):
    for candidate in (Path(path), Path(os.path.realpath(path))):
        for part in candidate.parts:
            lowered = part.lower()
            if lowered in _SENSITIVE_GIT_PARTS or lowered.endswith('.sock'):
                return True
    return False

def _read_git_text(path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('Metadados Git inválidos para o teste.')
    data = path.read_bytes()
    if len(data) > 4096 or b'\x00' in data:
        raise RuntimeError('Metadados Git inválidos para o teste.')
    return data.decode(errors='replace').strip()

def _git_admin_dir(path):
    path = Path(path)
    return path.is_dir() and not path.is_symlink() and ((path/'HEAD').is_file() or (path/'commondir').is_file() or (path/'objects').is_dir())

def _assert_git_metadata(path):
    """Validated development Git directory. Never production, a socket or credentials."""
    path = Path(os.path.abspath(path))
    if _sensitive_git_path(path):
        raise RuntimeError('Metadados Git sensíveis não são montados nos testes.')
    if path.is_symlink() or not path.is_dir() or not _git_admin_dir(path):
        raise RuntimeError('Metadados Git inválidos para o teste.')
    if not _under_dev_roots(path) or _in_production(path):
        raise RuntimeError('Metadados Git fora dos clones de desenvolvimento.')
    objects = path/'objects'
    if objects.is_symlink() and (not _under_dev_roots(objects) or _in_production(objects) or _sensitive_git_path(objects)):
        raise RuntimeError('Metadados Git fora dos clones de desenvolvimento.')
    return Path(os.path.abspath(path))

def _outermost_dirs(paths):
    ordered = []
    for path in paths:
        if path not in ordered:
            ordered.append(path)
    return [path for path in ordered if not any(path != other and other in path.parents for other in ordered)]

def git_check_mounts(cwd):
    """Read-only mounts that let git diff --check see a normal repo or a linked worktree.

    The worktree is mounted at /work. A linked worktree's .git file stores an absolute
    gitdir, usually under the development clone's .git/worktrees/<name>. That metadata
    is not inside /work, so it is mounted at the same absolute path. The mount source
    has to be the Git directory, not the main working tree, production, credentials or
    the Docker socket.
    """
    cwd = Path(cwd).resolve()
    if not cwd.is_dir() or not _under_dev_roots(cwd) or _in_production(cwd):
        raise RuntimeError('Use um clone de desenvolvimento em workspace/ ou worktrees/, não produção.')
    pointer = cwd/'.git'
    if not pointer.exists():
        return []
    if pointer.is_symlink():
        raise RuntimeError('Metadados Git via symlink não são montados nos testes.')
    if pointer.is_dir():
        _assert_git_metadata(pointer)
        return [(pointer, Path('/work/.git'))]
    text = _read_git_text(pointer)
    if not text.startswith('gitdir:'):
        raise RuntimeError('Metadados Git inválidos para o teste.')
    raw = text.split(':', 1)[1].strip()
    if not raw or not Path(raw).is_absolute():
        raise RuntimeError('Metadados Git do worktree precisam de gitdir absoluto dentro dos clones de desenvolvimento.')
    git_dir = _assert_git_metadata(Path(os.path.abspath(raw)))
    if git_dir == cwd or git_dir in cwd.parents:
        raise RuntimeError('Metadados Git fora dos clones de desenvolvimento.')
    common = git_dir
    marker = git_dir/'commondir'
    if marker.exists():
        common_raw = _read_git_text(marker)
        common_path = Path(common_raw)
        if not common_path.is_absolute():
            common_path = git_dir/common_path
        common = _assert_git_metadata(Path(os.path.abspath(common_path)))
        if common == cwd or common in cwd.parents:
            raise RuntimeError('Metadados Git fora dos clones de desenvolvimento.')
    mounts = [(pointer, Path('/work/.git'))]
    for directory in _outermost_dirs([common, git_dir]):
        mounts.append((directory, directory))
    return mounts

def test_commands(cwd, commands, timeout=120):
    from .validation_jobs import command
    return command(cwd,commands,timeout)

def _run_test_commands(cwd, commands, timeout=120):
    results = []
    # Resolve before any container starts so an unsafe gitdir never reaches Docker.
    git_mounts = git_check_mounts(cwd)
    git_mount_args = []
    for src, dst in git_mounts:
        git_mount_args.extend(['--mount', f'type=bind,src={src},dst={dst},readonly'])
    # Each invocation is ephemeral; package-manager downloads must survive
    # between provisioning and the subsequent offline checks.
    cache = STATE/'test-caches'/hashlib.sha256(str(Path(cwd).resolve()).encode()).hexdigest()[:20]
    for name in ('corepack','npm','pnpm','prisma','go-build','go-mod','go-tmp'):
        (cache/name).mkdir(parents=True,exist_ok=True,mode=0o700)
    # The runtime mounted for tests follows the project's .nvmrc major when an
    # installed runtime exists; engine-strict projects reject any other major.
    node=NODE
    try:
        major=(Path(cwd)/'.nvmrc').read_text().strip().lstrip('v').split('.')[0]
        if major.isdigit() and Path(f'/home/enok/.local/share/node{major}/bin/node').is_file():
            node=f'/home/enok/.local/share/node{major}/bin/node'
    except OSError: pass
    for command in commands:
        from .operator_hold import require_running
        require_running()
        # Dependency provisioning is separate from the offline checks: registry
        # downloads need networking, but never package lifecycle scripts, host
        # credentials, or a host-network connection.
        installation=(command[:2]==['npm','ci'] or command[:2]==['pnpm','install'] or command[:3]==['corepack','pnpm','install'])
        prisma_generation=command[:3]==['node','node_modules/prisma/build/index.js','generate']
        # `go [-C dir] mod download` fills the module cache; later Go checks stay offline.
        go_command=command[0]=='go'
        go_download=go_command and any(command[i:i+2]==['mod','download'] for i in range(len(command)))
        provisioning=installation or prisma_generation or go_download
        effective=[*command,'--ignore-scripts'] if installation and '--ignore-scripts' not in command else command
        # Tests cannot see production paths, host credentials, Docker socket or network.
        container_name = 'paseo-flow-test-' + uuid.uuid4().hex
        argv = ['docker','run','--name',container_name,'--label','paseo.validation.managed=true','--label','paseo.validation.job='+os.environ.get('PASEO_VALIDATION_JOB',''),'--pull','never','--rm','--network','host' if provisioning else 'none','--user','1000:1000','--cap-drop','ALL',
                '--security-opt','no-new-privileges','--security-opt','seccomp=/home/enok/srv_projetos/config/seccomp-default.json','--read-only','--memory','1536m' if command[0] in {'npm','node','pnpm','corepack','go'} else '384m','--cpus','2' if go_command else '1',
                '--pids-limit','256','--tmpfs','/tmp:rw,nosuid,size=128m',
                '--mount',f'type=bind,src={node},dst=/usr/local/bin/node,readonly',
                '--mount',f'type=bind,src={cwd},dst=/work','--workdir','/work',
                *git_mount_args,
                '--mount',f'type=bind,src={cache}/corepack,dst=/tmp/.corepack',
                '--mount',f'type=bind,src={cache}/npm,dst=/tmp/.npm',
                '--mount',f'type=bind,src={cache}/pnpm,dst=/tmp/.pnpm-store',
                '--mount',f'type=bind,src={cache}/prisma,dst=/tmp/.cache/prisma',
                # /tmp/.cache is created root-owned for the prisma mount and /tmp is a
                # 128 MiB tmpfs, so Go build, module and work caches need their own mounts.
                '--mount',f'type=bind,src={cache}/go-build,dst=/tmp/go-build',
                '--mount',f'type=bind,src={cache}/go-mod,dst=/tmp/go-mod',
                '--mount',f'type=bind,src={cache}/go-tmp,dst=/tmp/go-tmp',
                '--env','GOCACHE=/tmp/go-build','--env','GOMODCACHE=/tmp/go-mod','--env','GOTMPDIR=/tmp/go-tmp',
                # Go must not walk the external gitdir. Git metadata is mounted read-only
                # above; the requested command, including git diff --check, stays intact.
                '--env','GOFLAGS=-buildvcs=false','--env','GOTOOLCHAIN=local',
                '--env','GOPROXY='+('https://proxy.golang.org,direct' if go_download else 'off'),
                '--env','HOME=/tmp','--env','npm_config_cache=/tmp/.npm',
                '--env','CI=true','--env','npm_config_store_dir=/tmp/.pnpm-store',
                '--env','COREPACK_HOME=/tmp/.corepack','--env','NODE_OPTIONS=--max-old-space-size=1024',
                '--env','GIT_OPTIONAL_LOCKS=0',
                '--env','GIT_CONFIG_COUNT=2','--env','GIT_CONFIG_KEY_0=safe.directory','--env','GIT_CONFIG_VALUE_0=*',
                '--env','GIT_CONFIG_KEY_1=core.hooksPath','--env','GIT_CONFIG_VALUE_1=/dev/null',
                '--env','PYTHONDONTWRITEBYTECODE=1','--env','PYTEST_ADDOPTS=-p no:cacheprovider',RUNNER_IMAGE,*effective]
        started=now()
        try:
            # Cold Go builds with -race exceed the generic two-minute check budget.
            proc=subprocess.run(argv,capture_output=True,text=True,timeout=max(timeout,900) if go_command else timeout)
            result={'command':command,'kind':'dependency_setup' if provisioning else 'check','effective_command':effective,'exit_code':proc.returncode,'stdout':proc.stdout[-12000:],'stderr':proc.stderr[-12000:],'seconds':now()-started}
        except subprocess.TimeoutExpired:
            result={'command':command,'exit_code':124,'stderr':'Test timeout','seconds':now()-started}
        finally:
            # Killing the docker client does not stop its container. Cleanup is
            # scoped to this unique test container, never to production containers.
            subprocess.run(['docker','rm','-f',container_name],capture_output=True,timeout=15)
        results.append(result)
        if result['exit_code']: break
    return results

def checked_files(task):
    spec=decode(task['spec']); cwd=task['cwd']
    if task['branch'] and git(cwd,'branch','--show-current') != task['branch']:
        raise RuntimeError('Executor mudou a branch da worktree; integração bloqueada.')
    base=task['base_commit'] if 'base_commit' in task.keys() and task['base_commit'] else 'HEAD'
    tracked=[name for name in git(cwd,'diff','--name-only','-z',base).split('\x00') if name]
    untracked=[name for name in git(cwd,'ls-files','--others','--exclude-standard','-z').split('\x00') if name]
    extra=[name for name in set(tracked+untracked) if name not in {'.paseo-result.json','.paseo-review.json'}
           and not any(fnmatch.fnmatch(name,pattern) for pattern in spec['allowed_files'])]
    if extra: raise RuntimeError('Alterações fora do escopo aprovado: '+', '.join(extra))
    for name in set(tracked+untracked):
        path=Path(cwd)/name
        if path.is_symlink() or not path.resolve().is_relative_to(Path(cwd).resolve()):
            raise RuntimeError('Symlink/arquivo fora da worktree: '+name)
        if '.git' in Path(name).parts: raise RuntimeError('Metadados Git fora do escopo.')

def worktree_digest(cwd):
    names=set(name for name in git(cwd,'ls-files','-z').split('\x00') if name)
    names.update(name for name in git(cwd,'ls-files','--others','--exclude-standard','-z').split('\x00') if name)
    digest=hashlib.sha256()
    for name in sorted(names- {'.paseo-result.json','.paseo-review.json'}):
        path=Path(cwd)/name
        digest.update(name.encode()+b'\x00')
        if path.is_symlink():
            # Existing tracked links are project data. Hash the link itself,
            # never follow it into files outside the approved worktree.
            digest.update(b'<symlink>\x00'+os.readlink(path).encode()+b'\x00')
        elif path.is_file():
            with path.open('rb') as handle:
                for block in iter(lambda: handle.read(65536),b''):digest.update(block)
        else: digest.update(b'<deleted>')
    return digest.hexdigest()

def read_result(cwd, name):
    path=Path(cwd)/name
    if path.is_symlink() or path.stat().st_size>1024*1024:
        raise RuntimeError('Resultado estruturado inválido ou muito grande.')
    result=json.loads(path.read_text())
    if not isinstance(result,dict): raise RuntimeError('Resultado estruturado deve ser objeto JSON.')
    return result

def archive_worker(db,task):
    if not task['agent_id']: return
    try:
        ack=bridge('archive',agentId=task['agent_id'])
        if not isinstance(ack,dict) or not isinstance(ack.get('archivedAt'),str) or not ack['archivedAt']:
            raise RuntimeError('Archive did not return a terminal archivedAt acknowledgement')
        proof={'agent_id':task['agent_id'],'archivedAt':ack['archivedAt']}
        event(db,'worker_archived',proof,task['job_id'],task['id'])
        return proof
    except Exception as exc:
        event(db,'worker_archive_failed',{'agent_id':task['agent_id'],'error':str(exc)[-1000:]},task['job_id'],task['id'])

def extend_review_budget(db, task, error):
    """New actionable review findings get one correction; repeated findings go to manager."""
    if not autonomy_policy().get('unattended_development') or not str(error).startswith('Revisão reprovou: '):return False
    try: review=json.loads(str(error).split(': ',1)[1])
    except (ValueError,IndexError):return False
    issues=review.get('issues')
    if review.get('decision')!='fail' or not isinstance(issues,list) or not issues:return False
    if not all(isinstance(i,dict) and i.get('file') and i.get('requested_change') for i in issues):return False
    signature=hashlib.sha256(encoded(issues).encode()).hexdigest()
    for row in db.execute("SELECT data FROM events WHERE task_id=? AND kind='review_correction_budget_extended'",(task['id'],)):
        if decode(row['data']).get('signature')==signature:return False
    job=db.execute('SELECT * FROM jobs WHERE id=?',(task['job_id'],)).fetchone()
    if not job['approved'] or job['state'] not in ('running','blocked'):return False
    spec=decode(task['spec']);spec['max_attempts']=task['attempt']+1
    plan=decode(job['plan']);plan['tasks']=[spec if item['id']==task['task_key'] else item for item in plan['tasks']]
    plan_hash=hashlib.sha256(encoded(plan).encode()).hexdigest()
    db.execute('UPDATE tasks SET spec=? WHERE id=?',(encoded(spec),task['id']))
    db.execute('UPDATE jobs SET plan=?,plan_hash=?,updated=? WHERE id=?',(encoded(plan),plan_hash,now(),job['id']))
    event(db,'review_correction_budget_extended',{'signature':signature,'max_attempts':spec['max_attempts'],'previous_plan_hash':job['plan_hash'],'plan_hash':plan_hash,'reason':'Nova reprovação independente com correção concreta; preservar feedback, escopo, worktree e revisão.'},job['id'],task['id'])
    return True

def failure(db,task,error):
    if task['phase']=='review':
        from .policy_runtime import explicit_quota_text
        if explicit_quota_text(error):
            from .reviewer_routes import note_session_quota
            if note_session_quota(db,dict(task),str(error)):return
    if task['phase']=='implement':
        from .policy_integration import policy_enabled, programmer_quota_handoff
        if policy_enabled() and programmer_quota_handoff(db,task,{'lastError':str(error)}):return
    spec=decode(task['spec']); max_attempts=int(spec.get('max_attempts',3))
    model=task['review_model'] if task['phase']=='review' else task['model']
    if task['phase']=='review' and str(error).startswith(('Revisão reprovou','Regressão após revisão')):
        model=task['model'] # A reviewer finding a real defect is not a failed reviewer.
    job_plan=decode(db.execute('SELECT plan FROM jobs WHERE id=?',(task['job_id'],)).fetchone()['plan'])
    injected=db.execute("SELECT max(at) FROM events WHERE task_id=? AND kind='intentional_test_defect_injected'",(task['id'],)).fetchone()[0]
    synthetic=bool(job_plan.get('demo') is True and spec.get('inject_failure_once') and injected
               and injected>=(task['started'] or 0) and str(error).startswith('Testes falharam:'))
    from .worker_lifecycle import retire
    if not retire(db,task):return
    archive_proof=True
    if model and not synthetic: db.execute('INSERT INTO outcomes(model,task_id,success,latency,at) VALUES(?,?,?,?,?)',(model,task['id'],0,max(0,now()-(task['started'] or now())),now()))
    extra=task['attempt']>=max_attempts and (archive_proof or not task['agent_id']) and extend_review_budget(db,task,error)
    state='queued' if task['attempt']<max_attempts or extra else 'blocked'
    db.execute("UPDATE tasks SET state=?,phase='implement',previous_agent_id=agent_id,agent_id=NULL,launch_request=NULL,retry_at=?,error=?,updated=? WHERE id=?",
               (state,now()+min(60,5*max(task['attempt'],1)),str(error)[-16000:],now(),task['id']))
    if state=='blocked':db.execute('UPDATE jobs SET notified=0 WHERE id=?',(task['job_id'],))
    event(db,'correction_requested' if state=='queued' else 'task_blocked',{'error':str(error)[-8000:],'attempt':task['attempt'],'synthetic_fault_excluded_from_quality_history':synthetic},task['job_id'],task['id'])
    db.commit()
    from .validation_jobs import acknowledge_context
    acknowledge_context({'job':task['job_id'],'task':task['id'],'phase':task['phase'],'attempt':task['attempt']})

def finish_task(db,task,job):
    from .validation_jobs import CONTEXT,Pending
    CONTEXT.value={'job':job['id'],'task':task['id'],'phase':task['phase'],'attempt':task['attempt']}
    validation_context=dict(CONTEXT.value)
    spec=decode(task['spec']);cwd=Path(task['cwd'])
    try:
        checked_files(task)
        if task['phase']=='implement':
            result=read_result(cwd,'.paseo-result.json')
            if result.get('status')!='completed': raise RuntimeError('Executor bloqueado: '+encoded(result))
            # Only an explicitly marked disposable demo may inject this known defect.
            already_injected=db.execute("SELECT 1 FROM events WHERE task_id=? AND kind='intentional_test_defect_injected'",(task['id'],)).fetchone()
            if decode(job['plan']).get('demo') is True and spec.get('inject_failure_once') and not already_injected:
                if not (Path(job['repo'])/'.paseo-disposable-demo').is_file(): raise RuntimeError('Invalid demo marker')
                target=cwd/'sum_values.py'
                target.write_text('def sum_values(values):\n    return 0\n')
                event(db,'intentional_test_defect_injected',{'file':'sum_values.py'},job['id'],task['id'])
            policy=_plan_policy(job)
            checks=test_commands(str(cwd),spec['tests'])
            if policy is None:
                event(db,'tests_executed',{'results':checks},job['id'],task['id'])
                if not checks or any(check['exit_code'] for check in checks): raise RuntimeError('Testes falharam: '+encoded(checks))
                checked_files(task)
                digest=worktree_digest(str(cwd))
                payload={'implementation':result,'tests':checks,'implementation_seconds':max(0,now()-(task['started'] or now()))}
            else:
                compact=compact_results(checks)
                counts={'executed':len(checks),'reused':0}
                runner=runner_stamp(str(cwd), NODE)
                reason='checks essenciais executados pelo controlador após a implementação'
                if runner is None: reason+='; ambiente do runner não verificável e reuso não autorizado'
                event(db,'tests_executed',{'results':compact,'counts':counts,'reason':reason,'action':'executed'},job['id'],task['id'])
                if not checks or any(check['exit_code'] for check in checks): raise RuntimeError('Testes falharam: '+encoded(compact))
                checked_files(task)
                digest=worktree_digest(str(cwd))
                payload={'implementation':result,'tests':compact,'implementation_seconds':max(0,now()-(task['started'] or now())),'validation':{
                    'mode':'proportional_v1','phase':'implement','action':'executed','reason':reason,'digest':digest,
                    'commands':spec['tests'],'runner':runner,'checks':compact,'counts':counts,'passed':True}}
            from .worker_lifecycle import retire
            if not retire(db,task,'completed'):return
            db.execute("UPDATE tasks SET state='queued',phase='review',previous_agent_id=agent_id,agent_id=NULL,result=?,review_digest=?,error=NULL,updated=? WHERE id=?",
                       (encoded(payload),digest,now(),task['id']))
            event(db,'independent_review_requested',{},job['id'],task['id'])
            db.commit()
            from .validation_jobs import acknowledge_context
            acknowledge_context(validation_context)

        else:
            review=read_result(cwd,'.paseo-review.json')
            if review.get('decision')!='pass': raise RuntimeError('Revisão reprovou: '+encoded(review))
            if task['review_digest'] != worktree_digest(str(cwd)):
                raise RuntimeError('Revisor alterou o código; requer nova implementação/revisão.')
            # Repeat validation after review to detect edits during the review itself.
            checked_files(task)
            policy=_plan_policy(job)
            validation_note=None
            if policy is None:
                checks=test_commands(str(cwd),spec['tests'])
            else:
                checks,validation_note=_proportional_review_checks(db,task,spec,cwd)
            if any(check['exit_code'] for check in checks): raise RuntimeError('Regressão após revisão: '+encoded(checks))
            checked_files(task)
            if task['review_digest'] != worktree_digest(str(cwd)):
                raise RuntimeError('Comandos de teste modificaram o código após a revisão.')
            from .worker_lifecycle import retire
            if not retire(db,task,'completed'):return
            for name in ['.paseo-result.json','.paseo-review.json']:(cwd/name).unlink(missing_ok=True)
            git(cwd,'add','--all')
            if git(cwd,'diff','--cached','--name-only'):
                git(cwd,'-c','user.name=Paseo Development','-c','user.email=paseo@localhost','commit','-m',f"Task {task['task_key']}: {spec['objective'][:100]}")
            commit=git(cwd,'rev-parse','HEAD')
            result=decode(task['result']) or {}
            result.update(review=review,review_tests=checks,commit=commit,review_seconds=max(0,now()-(task['started'] or now())))
            if validation_note is not None: result['validation_review']=validation_note
            # Persist reviewed commit before merge, so crash recovery does not
            # depend on artifacts already removed from the working tree.
            db.execute("UPDATE tasks SET state='integrating',phase='integrate',result=?,commit_sha=?,updated=? WHERE id=?",
                       (encoded(result),commit,now(),task['id']))
            event(db,'integration_prepared',{'commit':commit},job['id'],task['id']);db.commit()
            from .validation_jobs import acknowledge_context
            acknowledge_context(validation_context)
            current=db.execute('SELECT * FROM tasks WHERE id=?',(task['id'],)).fetchone()

            integrate_task(db,current,job)
    except Pending as pending:
        if task['state']!='validating':event(db,'validation_running',{'operation':str(pending)},job['id'],task['id'])
        db.execute("UPDATE tasks SET state='validating',deadline=NULL,updated=? WHERE id=?",(now(),task['id']))
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc: failure(db,task,str(exc))
    db.commit()

def _proportional_review_checks(db, task, spec, cwd):
    """Reuse a passing controller run, or execute the essential checks with an explicit reason."""
    digest=worktree_digest(str(cwd))
    runner=runner_stamp(str(cwd), NODE)
    stored=decode(task['result']) or {}
    evidence=stored.get('validation') if isinstance(stored, dict) else None
    reuse, reason=reuse_decision(evidence, digest=digest, commands=spec['tests'], runner=runner)
    if reuse and digest!=task['review_digest']:
        reuse, reason=False, 'digest da revisão divergente'
    if reuse:
        checks=evidence['checks']
        counts={'executed':0,'reused':len(checks)}
        note={'mode':'proportional_v1','phase':'review','action':'reused','reason':reason,'digest':digest,
              'commands':spec['tests'],'runner':runner,'checks':checks,'counts':counts,'passed':True}
        event(db,'validation_reused',{'reason':reason,'counts':counts,'commands':spec['tests'],'runner':runner,'digest':digest},task['job_id'],task['id'])
        return checks, note
    checks=test_commands(str(cwd), spec['tests'])
    compact=compact_results(checks)
    counts={'executed':len(checks),'reused':0}
    passed=bool(checks) and not any(check.get('exit_code') for check in checks)
    note={'mode':'proportional_v1','phase':'review','action':'executed','reason':reason,'digest':digest,
          'commands':spec['tests'],'runner':runner,'checks':compact,'counts':counts,'passed':passed}
    event(db,'tests_executed',{'results':compact,'counts':counts,'reason':reason,'action':'executed'},task['job_id'],task['id'])
    return compact, note

def integrate_task(db, task, job):
    """Idempotent integration of a reviewed commit, then consolidated tests."""
    from .validation_jobs import CONTEXT,Pending
    CONTEXT.value={'job':job['id'],'task':task['id'],'phase':'integrate','commit':task['commit_sha']}
    from .operator_hold import active as held
    if held() or job['state']=='paused':return
    try:
        if git(job['repo'],'branch','--show-current')!=job['branch'] or not job['branch'].startswith('orchestration/'):
            raise RuntimeError('Branch de integração protegida ou alterada.')
        exclude_local_control_files(job['repo'])
        from .integration_owner import claim
        if not claim(db,task,job):return
        from .validation_jobs import context_running
        if context_running(CONTEXT.value):return
        dirty=git(job['repo'],'status','--porcelain')
        if dirty:raise RuntimeError(INTEGRATION_DIRTY_PREFIX+'\n'+dirty[:4000])
        commit=task['commit_sha']
        if not commit:raise RuntimeError('Commit revisado ausente; integração bloqueada.')
        try:
            git(job['repo'],'merge-base','--is-ancestor',commit,'HEAD')
            already_merged=True
        except subprocess.CalledProcessError:
            already_merged=False
        if not already_merged:
            try:
                git(job['repo'],'-c','user.name=Paseo Development','-c','user.email=paseo@localhost',
                    'merge','--no-edit','--no-ff',commit)
            except subprocess.CalledProcessError as exc:
                git(job['repo'],'merge','--abort')
                raise RuntimeError('Conflito de integração; precisa replanejamento: '+exc.stderr[-2000:])
        policy=_plan_policy(job)
        task_spec=decode(task['spec'])
        if policy is None:
            commands=[];seen=set()
            for row in db.execute("SELECT spec FROM tasks WHERE job_id=? AND (state='done' OR id=?) ORDER BY rowid",(job['id'],task['id'])):
                for command in decode(row['spec']).get('tests',[]):
                    key=encoded(command)
                    if key not in seen:commands.append(command);seen.add(key)
        else:
            commands=integration_commands(task_spec, policy)
            if not commands: raise RuntimeError('Tarefa optante sem checks essenciais.')
        baseline=worktree_digest(job['repo'])
        checks=test_commands(job['repo'],commands)
        head=git(job['repo'],'rev-parse','HEAD')
        if policy is None:
            event(db,'integration_tests_executed',{'results':checks,'already_merged':already_merged,
                  'integration_head':head},job['id'],task['id'])
            shown=checks
        else:
            shown=compact_results(checks)
            counts={'executed':len(checks),'reused':0}
            reason='checkpoint antecipado: checks da tarefa e suíte final no HEAD combinado' if task_spec.get('validation_checkpoint') is True else 'integração optante: somente checks essenciais desta tarefa no HEAD combinado'
            event(db,'integration_tests_executed',{'results':shown,'already_merged':already_merged,'integration_head':head,
                  'counts':counts,'reason':reason,'commands':commands},job['id'],task['id'])
        if not checks or any(check['exit_code'] for check in checks):
            raise RuntimeError('Testes consolidados falharam após integração: '+encoded(shown))
        if baseline!=worktree_digest(job['repo']) or git(job['repo'],'status','--porcelain'):
            raise RuntimeError('Testes consolidados modificaram a branch de integração.')
        result=decode(task['result']) or {}
        result['integration_tests']=shown
        result['integration_head']=head
        if policy is not None:
            runner=runner_stamp(job['repo'], NODE)
            result['validation_integration']={'mode':'proportional_v1','action':'executed','reason':reason,'commands':commands,
                'head':head,'digest':baseline,'runner':runner,'counts':counts,'passed':True}
            if task_spec.get('validation_checkpoint') is True and runner and runner.get('id') and commands_cover(commands, policy['final_tests']):
                event(db,'final_validation',{'mode':'proportional_v1','action':'executed','passed':True,
                    'reason':'suíte final executada no checkpoint da tarefa','head':head,'digest':baseline,
                    'commands':policy['final_tests'],'runner':runner,
                    'counts':{'executed':len(policy['final_tests']),'reused':0}},job['id'],task['id'])
        db.execute("UPDATE tasks SET state='done',result=?,error=NULL,updated=? WHERE id=?",(encoded(result),now(),task['id']))
        for model in [task['model'],task['review_model']]:
            if model:db.execute('INSERT INTO outcomes(model,task_id,success,latency,at) VALUES(?,?,?,?,?)',
                (model,task['id'],1,result.get('implementation_seconds' if model==task['model'] else 'review_seconds'),now()))
        event(db,'task_integrated',{'commit':commit,'branch':job['branch']},job['id'],task['id'])
        db.commit()
        from .validation_jobs import acknowledge_context
        acknowledge_context(CONTEXT.value)
        from .integration_owner import release
        release(db,task,job)
    except Pending:
        pass
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        # Preserve the dev branch and evidence; never reset main or production.
        db.execute("UPDATE tasks SET state='blocked',error=?,updated=? WHERE id=?",(str(exc)[-16000:],now(),task['id']))
        db.execute("UPDATE jobs SET state='blocked',updated=? WHERE id=?",(now(),job['id']))
        event(db,'integration_blocked',{'error':str(exc)[-8000:],'branch':job['branch']},job['id'],task['id'])
        db.commit()
        from .validation_jobs import acknowledge_context
        acknowledge_context(CONTEXT.value)
    db.commit()

def native_snapshot(agent_id):
    value=bridge('agent',agentId=agent_id)
    return value.get('agent',value) if isinstance(value,dict) else value

def review_quota_handoff(db, task, snapshot):
    """Switch only the reviewer when this review turn exhausted quota.

    Idle and closed turns carry the same explicit limit as error/failed.
    Missing .paseo-review.json is not an implementation defect in that case.
    """
    if task['phase'] != 'review':
        return False
    from .reviewer_routes import note_session_quota, quota_failure_reason
    catalog_doc=None
    try: catalog_doc=json.loads((STATE/'catalog.json').read_text())
    except (OSError, ValueError): catalog_doc=None
    evidence=quota_failure_reason(task, snapshot, catalog_doc)
    if not evidence:
        return False
    err=str(snapshot.get('lastError') or snapshot.get('error') or '')
    return bool(note_session_quota(db, task, err or 'quota exhausted', evidence))

def reconcile(db):
    from .worker_lifecycle import reconcile_orphans
    reconcile_orphans(db)
    from .policy_integration import retry_quota_publications
    retry_quota_publications(db)
    from .policy_integration import retry_pending_releases
    retry_pending_releases(db)
    # Local supervisor metadata must not strand an already reviewed commit.
    # Once the tree is clean, recover this pre-merge failure without a new agent.
    # Real test failures, merge conflicts, changed commits and pauses stay blocked.
    if autonomy_policy().get('unattended_development') is True:
        pending=db.execute("SELECT tasks.* FROM tasks JOIN jobs ON jobs.id=tasks.job_id WHERE tasks.state='blocked' AND tasks.phase='integrate' AND jobs.state IN ('running','blocked') AND jobs.approved IS NOT NULL").fetchall()
        for task in pending:
            if not (task['error'] or '').startswith(INTEGRATION_DIRTY_PREFIX):continue
            job=db.execute('SELECT * FROM jobs WHERE id=?',(task['job_id'],)).fetchone()
            try:validate_integration_recovery(task,job)
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):continue
            db.execute("UPDATE tasks SET state='integrating',error=NULL,updated=? WHERE id=?",(now(),task['id']))
            db.execute("UPDATE jobs SET state='running',notified=0,updated=? WHERE id=?",(now(),job['id']))
            event(db,'integration_recovered_automatically',{'commit':task['commit_sha'],'previous_error':task['error'],'attempts_preserved':task['attempt']},job['id'],task['id'])
        db.commit()
    tasks=db.execute("SELECT * FROM tasks WHERE state IN ('running','launching','waiting_permission','integrating','validating') ORDER BY started,id").fetchall()
    for task in tasks:
        job=db.execute('SELECT * FROM jobs WHERE id=?',(task['job_id'],)).fetchone()
        if job['state']=='paused':continue
        if task['state']=='validating':
            finish_task(db,task,job);continue
        if task['state']=='integrating':
            job=db.execute('SELECT * FROM jobs WHERE id=?',(task['job_id'],)).fetchone()
            integrate_task(db,task,job);continue
        if not task['agent_id']:
            if task['state']=='launching' and task['launch_request']:
                if not task['retry_at'] or now()>=task['retry_at']:
                    job=db.execute('SELECT * FROM jobs WHERE id=?',(task['job_id'],)).fetchone()
                    try:launch(db,task,job,[])
                    except LaunchUncertain:pass
                continue
            db.execute("UPDATE tasks SET state='queued' WHERE id=?",(task['id'],));continue
        if task['deadline'] and now()>task['deadline']:
            bridge('stop',agentId=task['agent_id'])
            failure(db,task,'Prazo máximo excedido.');continue
        try:snapshot=native_snapshot(task['agent_id'])
        except (RuntimeError,subprocess.SubprocessError) as exc:
            event(db,'connection_unavailable',{'error':str(exc)},task['job_id'],task['id']);continue
        if not isinstance(snapshot,dict):continue
        state=snapshot.get('status') or snapshot.get('lifecycle')
        pending=snapshot.get('pendingPermissions') or snapshot.get('pendingPermissionRequests')
        if pending:
            from .permissions import approve_routine
            approve_routine(snapshot,db=db)
        if pending:
            if task['permission_wait_at'] is None:
                remaining=max(0,(task['deadline'] or now()+decode(task['spec']).get('timeout_seconds',900))-now())
                db.execute("UPDATE tasks SET state='waiting_permission',observed_running=1,permission_wait_at=?,deadline_remaining=?,deadline=NULL,updated=? WHERE id=?",
                           (now(),remaining,now(),task['id']))
                event(db,'execution_paused_for_permission',{'remaining_execution_seconds':remaining},task['job_id'],task['id'])
            continue
        if task['permission_wait_at'] is not None:
            db.execute('UPDATE tasks SET deadline=?,permission_wait_at=NULL,deadline_remaining=NULL WHERE id=?',
                       (now()+max(1,task['deadline_remaining'] or 0),task['id']))
            event(db,'execution_resumed_after_permission',{'waiting_seconds':max(0,now()-task['permission_wait_at'])},task['job_id'],task['id'])
        if state in {'initializing','starting'} and not snapshot.get('activeTurn'):
            continue
        if state == 'running' or snapshot.get('activeTurn'):
            db.execute("UPDATE tasks SET state='running',observed_running=1 WHERE id=?",(task['id'],))
            continue
        if state in {'error','failed','idle','closed'} and task['phase']=='implement':
            from .policy_integration import policy_enabled, programmer_quota_handoff
            if policy_enabled() and programmer_quota_handoff(db, task, snapshot):
                continue
        if state in {'error','failed'}:
            if review_quota_handoff(db, task, snapshot):
                continue
            err=str(snapshot.get('lastError') or snapshot.get('error') or '')
            failure(db,task,err or 'Provider failure');continue
        if state in {'idle','closed'}:
            # Native create can return an idle snapshot before initialPrompt has
            # started. A fresh artifact or observed running/finished event is
            # needed before interpreting idle as task completion.
            artifact=Path(task['cwd'])/('.paseo-review.json' if task['phase']=='review' else '.paseo-result.json')
            # An idle/closed review can end on quota without status error/failed.
            # Recognize that before a missing review file becomes a Grok correction.
            # A review file already on disk is still a real review result.
            if task['phase']=='review' and not artifact.is_file() and review_quota_handoff(db, task, snapshot):
                continue
            completed=bool(task['observed_running'] or artifact.is_file() or snapshot.get('attentionReason')=='finished')
            if not completed:continue
            if state=='idle' and not artifact.exists() and not snapshot.get('lastError'):
                # A provider may end a turn before writing its completion file.
                # Continue the SAME session once, without spending another attempt.
                nudges=db.execute("SELECT at,data FROM events WHERE task_id=? AND kind='completion_artifact_requested' ORDER BY seq DESC",(task['id'],)).fetchall()
                nudge=next((r for r in nudges if decode(r['data']).get('attempt')==task['attempt'] and decode(r['data']).get('phase')==task['phase']),None)
                if not nudge:
                    event(db,'completion_artifact_requested',{'attempt':task['attempt'],'phase':task['phase'],'agent_id':task['agent_id']},task['job_id'],task['id'])
                    db.commit()
                    try:
                        bridge('send',agentId=task['agent_id'],prompt=f"Seu turno encerrou sem {artifact.name}. Continue esta mesma tarefa na worktree {task['cwd']}; preserve as alterações existentes, conclua implementação/verificações e grave o resultado exigido no pedido inicial. Se houver impedimento real, registre-o no arquivo; não declare sucesso sem verificar. Esta é uma continuação da tentativa atual, não um novo plano.")
                    except Exception as exc:
                        event(db,'completion_artifact_delivery_uncertain',{'error':str(exc)[-1000:]},task['job_id'],task['id'])
                    continue
                if now()-nudge['at']<15:continue
            job=db.execute('SELECT * FROM jobs WHERE id=?',(task['job_id'],)).fetchone()
            finish_task(db,task,job)
    db.commit()

def cleanup_completed_workspaces(db,job):
    """Archive only integrated, clean task worktrees after the whole job succeeds."""
    if not autonomy_policy().get('archive_completed_workspaces'):return
    rows=db.execute('SELECT * FROM tasks WHERE job_id=?',(job['id'],)).fetchall()
    if not rows or any(t['state']!='done' for t in rows):return
    for task in rows:
        if not task['workspace_id'] or not task['cwd'] or not task['commit_sha']:continue
        path=Path(task['cwd']).resolve()
        if not path.is_relative_to(WORKTREES.resolve()) or str(path)==job['repo']:continue
        try:
            if path.exists():
                if git(path,'status','--porcelain'):raise RuntimeError('Worktree contém alterações não integradas')
                git(job['repo'],'merge-base','--is-ancestor',git(path,'rev-parse','HEAD'),'HEAD')
            bridge('workspace-archive',workspaceId=task['workspace_id'])
            event(db,'completed_workspace_archived',{'workspace_id':task['workspace_id'],'cwd':str(path)},job['id'],task['id'])
        except Exception as exc:
            event(db,'workspace_cleanup_deferred',{'workspace_id':task['workspace_id'],'error':str(exc)[-500:]},job['id'],task['id'])
    # An empty project card is redundant; preserve any workspace opened by a user
    # or another job, and never remove the main workspace project.
    try:
        workspaces=bridge('workspaces',options={'includeBackground':True}).get('entries',[])
        for project in bridge('projects').get('projects',[]):
            if project.get('projectRootPath')!=job['repo'] or project.get('projectRootPath')==str(DEV):continue
            if any(w.get('projectId')==project['projectId'] for w in workspaces):continue
            bridge('project-remove',projectId=project['projectId'])
    except Exception as exc:
        event(db,'project_cleanup_deferred',{'error':str(exc)[-500:]},job['id'])

# Each chat has its own ten workers. Chat identity is supervisor_id across jobs.
# A job with no supervisor is isolated by job_id. Reviewers count.
PER_CHAT_WORKERS=10

def chat_admission_key(supervisor_id, job_id):
    return ('supervisor', supervisor_id) if supervisor_id else ('job', job_id)

def _row_field(row, name):
    return row.get(name) if isinstance(row, dict) else row[name]

def active_workers_for_chat(rows, supervisor_id, job_id):
    key=chat_admission_key(supervisor_id, job_id)
    total=0
    for row in rows:
        if _row_field(row, 'state') not in {'running','launching','waiting_permission','validating'}:continue
        if chat_admission_key(_row_field(row, 'supervisor_id'), _row_field(row, 'job_id'))==key:total+=1
    return total

def chat_at_worker_cap(rows, supervisor_id, job_id, limit=PER_CHAT_WORKERS):
    return active_workers_for_chat(rows, supervisor_id, job_id)>=limit

def _latest_final_proof(db, job_id):
    row=db.execute("SELECT data FROM events WHERE job_id=? AND kind='final_validation' ORDER BY seq DESC LIMIT 1",(job_id,)).fetchone()
    return decode(row['data']) if row else None

def _block_final(db, job, diagnosis, counts=None):
    """Block the job only. Completed tasks, commits and attempts stay as they are."""
    payload={'error':str(diagnosis)[-8000:],'preserve_completed_tasks':True,'attempts_preserved':True}
    if counts: payload['counts']=counts
    db.execute("UPDATE jobs SET state='blocked',updated=? WHERE id=?",(now(),job['id']))
    event(db,'final_validation_blocked',payload,job['id'])
    db.commit()
    from .validation_jobs import CONTEXT,acknowledge_context
    context=getattr(CONTEXT,'value',None) or {}
    if context.get('job')==job['id'] and context.get('phase')=='final':acknowledge_context(context)

def _final_checkpoint(db, job, policy):
    from .validation_jobs import CONTEXT
    CONTEXT.value={'job':job['id'],'phase':'final','head':git(job['repo'],'rev-parse','HEAD')}
    repo=job['repo']
    from .validation_jobs import context_running,Pending
    if context_running(CONTEXT.value):raise Pending('final_runner_running')
    dirty=git(repo,'status','--porcelain')
    if dirty:
        _block_final(db, job, 'Checkpoint final exige árvore limpa no HEAD combinado.\n'+dirty[:500])
        return False
    head=git(repo,'rev-parse','HEAD')
    digest=worktree_digest(repo)
    runner=runner_stamp(repo, NODE)
    commands=policy['final_tests']
    previous=_latest_final_proof(db, job['id'])
    if proof_valid(previous, head=head, digest=digest, commands=commands, runner=runner):
        event(db,'final_validation',{'mode':'proportional_v1','action':'reused','passed':True,
            'reason':'prova final ainda válida para este HEAD, digest, comandos e runner',
            'head':head,'digest':digest,'commands':commands,'runner':runner,
            'counts':{'executed':0,'reused':len(commands)}},job['id'])
        return True
    if runner is None:
        _block_final(db, job, 'Ambiente do runner não verificável; checkpoint final não autoriza pular a suíte.')
        return False
    checks=test_commands(repo, commands)
    compact=compact_results(checks)
    counts={'executed':len(checks),'reused':0}
    if worktree_digest(repo)!=digest or git(repo,'status','--porcelain'):
        event(db,'final_validation',{'mode':'proportional_v1','action':'executed','passed':False,
            'reason':'testes finais modificaram a branch de integração','head':head,'digest':digest,
            'commands':commands,'runner':runner,'counts':counts},job['id'])
        _block_final(db, job, 'Testes finais modificaram a branch de integração.', counts)
        return False
    if not checks or any(check.get('exit_code') for check in checks):
        event(db,'final_validation',{'mode':'proportional_v1','action':'executed','passed':False,
            'reason':'suíte final falhou no HEAD combinado','head':head,'digest':digest,
            'commands':commands,'runner':runner,'counts':counts,'results':compact},job['id'])
        _block_final(db, job, 'Checkpoint final falhou: '+encoded(compact), counts)
        return False
    event(db,'final_validation',{'mode':'proportional_v1','action':'executed','passed':True,
        'reason':'suíte final executada uma vez no HEAD combinado','head':head,'digest':digest,
        'commands':commands,'runner':runner,'counts':counts,'results':compact},job['id'])
    db.commit()
    from .validation_jobs import acknowledge_context
    acknowledge_context(CONTEXT.value)
    return True

def _job_ready_to_complete(db, job):
    """Legacy jobs complete immediately. Opt-in jobs need one valid final proof."""
    try: policy=_plan_policy(job)
    except ValueError as exc:
        _block_final(db, job, 'Política de validação inválida: '+str(exc))
        return False
    if policy is None: return True
    from .validation_jobs import Pending
    try: return _final_checkpoint(db, job, policy)
    except Pending:return False
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        _block_final(db, job, 'Checkpoint final bloqueado: '+str(exc))
        return False

@serialized
def tick():
    from .operator_hold import active as held
    if held():return {'allowed':False,'reasons':['operator_hold']}
    with database() as db:
        reconcile(db)
        for job in db.execute("SELECT * FROM jobs WHERE state='running'").fetchall():
            tasks=db.execute('SELECT * FROM tasks WHERE job_id=?',(job['id'],)).fetchall()
            states={t['task_key']:t['state'] for t in tasks}
            if all(s=='done' for s in states.values()):
                if _job_ready_to_complete(db, job):
                    db.execute("UPDATE jobs SET state='done',updated=? WHERE id=?",(now(),job['id']))
                    event(db,'job_completed',{'branch':job['branch']},job['id'])
                    db.commit()
                    cleanup_completed_workspaces(db,job)
                continue
            active=any(s in {'running','launching','waiting_permission','integrating','validating'} for s in states.values())
            ready=any(t['state']=='queued' and all(states[dep]=='done' for dep in decode(t['spec']).get('depends_on',[])) for t in tasks)
            if any(s=='blocked' for s in states.values()) and not active and not ready:
                db.execute("UPDATE jobs SET state='blocked',updated=? WHERE id=?",(now(),job['id']))
                event(db,'job_blocked',{},job['id']);continue
        from .policy_integration import _chat_expr
        active_rows=db.execute(f"""SELECT tasks.*, {_chat_expr(db)} AS chat_id, jobs.supervisor_id AS supervisor_id
            FROM tasks JOIN jobs ON jobs.id=tasks.job_id
            LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id
            WHERE tasks.state IN ('running','launching','waiting_permission','validating')""").fetchall()
        active=[t['review_model'] if t['phase']=='review' else t['model'] for t in active_rows if t['model'] or t['review_model']]
        sample=sample_resources(previous=getattr(tick,'previous_sample',None))
        tick.previous_sample=sample
        from .policy_integration import adopt_running_gpt, policy_enabled, resource_config
        envelope=resource_config(db) if policy_enabled() else None
        if envelope is not None:
            adopt_running_gpt(db)
        resources=assess_resources(config=envelope, active_workers=len(active_rows),sample=sample)
        if set(resources.get('reasons',[])) & {'insufficient_disk_space','disk_usage_high'} and autonomy_policy().get('unattended_development') is True:
            from .maintenance import reclaim_completed_dependencies
            maintenance=reclaim_completed_dependencies(db)
            if maintenance['removed_paths']:
                sample=sample_resources(previous=sample);tick.previous_sample=sample
                resources=assess_resources(config=envelope, active_workers=len(active_rows),sample=sample)
                resources['maintenance']=maintenance
        (STATE/'resources.json').write_text(encoded(resources)+'\n')
        if resources['allowed']:
            candidates=db.execute("SELECT tasks.* FROM tasks JOIN jobs ON jobs.id=tasks.job_id WHERE tasks.state='queued' AND jobs.state='running' ORDER BY tasks.rowid").fetchall()
            candidates=sorted(candidates,key=lambda t:-int(decode(t['spec']).get('priority',0)))
            for task in candidates:
                job=db.execute('SELECT * FROM jobs WHERE id=?',(task['job_id'],)).fetchone()
                if envelope is not None:
                    from .model_limits import load_limits
                    from .policy_integration import chat_worker_blocked
                    if chat_worker_blocked(active_rows, job, load_limits().get('workers_per_chat') or 10, db):
                        continue
                elif chat_at_worker_cap(active_rows, job['supervisor_id'], job['id']):
                    continue
                states={r['task_key']:r['state'] for r in db.execute('SELECT task_key,state FROM tasks WHERE job_id=?',(job['id'],))}
                if task['retry_at'] and now()<task['retry_at']:continue
                if any(states[dep]!='done' for dep in decode(task['spec']).get('depends_on',[])):continue
                try:launch(db,task,job,active)
                except LaunchUncertain:
                    pass # Durable exact request is reconciled; never increment or choose again.
                except ModelUnavailable as exc:
                    db.execute('UPDATE tasks SET retry_at=?,error=?,updated=? WHERE id=?',
                               (now()+60,((str(task['error']).split('; wait: ',1)[0] + '; wait: ' + str(exc)) if task['error'] else str(exc))[:16000],now(),task['id']))
                    event(db,'model_availability_wait',{'phase':task['phase'],'retry_seconds':60},job['id'],task['id'])
                except Exception as exc:
                    # Do not busy-loop a broken provider. Attempts and terminal blockers are durable.
                    task=dict(task);task['attempt']+=1
                    db.execute('UPDATE tasks SET attempt=? WHERE id=?',(task['attempt'],task['id']))
                    failure(db,task,str(exc))
                break # Fresh resource sample on next tick before a second admission.
        db.commit()
        completed=db.execute("""SELECT * FROM jobs WHERE notified=0 AND
            (state IN ('done','blocked') OR (state='running' AND EXISTS
             (SELECT 1 FROM tasks WHERE tasks.job_id=jobs.id AND
              (tasks.state='blocked' OR (tasks.state='launching' AND tasks.launch_failures>=3)))))""").fetchall()
        for job in completed:
            report(job['id'])
            if job['supervisor_id']:
                try:
                    bridge('send',agentId=job['supervisor_id'],prompt=f"Evento do controlador: plano {job['id']} está {job['state']}. Consulte `paseo-flow report {job['id']}` e a política vigente em model-limits.json. Você é o gerente responsável pela continuidade autônoma já autorizada. Se houver launch_requires_attention, investigue o erro da criação sem duplicar o executor nem descartar o recibo incerto. Se houver tarefa blocked, mesmo com outras executando, analise a causa e recupere o mesmo plano pelo controlador quando houver correção concreta dentro do escopo aprovado; inclua a reprovação completa no contexto do programador e amplie max_attempts uma tentativa por decisão justificada; não há teto global fixo de cinco. Não encerre apenas relatando um bloqueio recuperável. Se done, confira o backlog aprovado e planeje o próximo lote autorizado com tarefas independentes em paralelo. Preserve entregas concluídas e pausas explícitas do usuário. Gerente não programa: delegue ao programador selecionado pelo controlador e exija revisão independente. Papéis e ordem de programação: {__import__('orchestrator.model_limits',fromlist=['role_summary']).role_summary()} Se depender de decisão externa real ou de ampliar o escopo, explique o impedimento concreto. Atualize o usuário com resultados verificáveis.")
                except Exception as exc:
                    event(db,'notification_pending',{'error':str(exc)},job['id']);continue
            db.execute('UPDATE jobs SET notified=1 WHERE id=?',(job['id'],))
    return resources

def report(job_id):
    value=status(job_id)
    if not value:raise ValueError('Plano inexistente')
    with database() as db:
        events=[{**dict(row),'data':decode(row['data'])} for row in db.execute('SELECT * FROM events WHERE job_id=? ORDER BY seq',(job_id,))]
    out=STATE/'reports';out.mkdir(exist_ok=True)
    data={'job':value[0],'events':events,'generated_at':now()}
    (out/(job_id+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    job=value[0]
    lines=[f"# {job['objective']}",f"Estado: {job['state']}",f"Branch de desenvolvimento: `{job['branch']}`",'', '| Tarefa | Estado | Modelo | Tentativas |','|---|---|---|---|']
    for task in job['tasks']:lines.append(f"| {task['task_key']} | {task['state']} | {task['model']} | {task['attempt']} |")
    lines+=['','Evidências completas: '+str(out/(job_id+'.json'))]
    (out/(job_id+'.md')).write_text('\n'.join(lines)+'\n')
    return data
