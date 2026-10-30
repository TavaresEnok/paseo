"""Private, narrow supervisor API plus an event-driven durable scheduler."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
import secrets
from pathlib import Path
import threading
import time
import traceback

from . import core
from .routing import select_for_task
from .summaries import compact_report,overview

TOKEN_FILE = Path('/home/enok/srv_projetos/runtime/isolated/flow-token')
WAKE = threading.Event()

def ensure_api_token():
    TOKEN_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        fd=os.open(TOKEN_FILE,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        if TOKEN_FILE.is_symlink() or not TOKEN_FILE.is_file() or not TOKEN_FILE.read_text().strip():
            raise RuntimeError('Token local da API inválido; credencial existente preservada.')
        TOKEN_FILE.chmod(0o600)
    else:
        with os.fdopen(fd,'w') as handle:handle.write(secrets.token_urlsafe(32)+'\n')


def require_manager(agent_id,job_id=None):
    if not agent_id:raise ValueError('Gerente obrigatório.')
    with core.database() as db:
        ticket=db.execute("SELECT chat_id,role FROM admission_tickets WHERE agent_id=?",(agent_id,)).fetchone()
        if not ticket or ticket['role']!='manager':raise ValueError('Operação reservada ao gerente vigente.')
        owner=db.execute('SELECT agent_id FROM manager_owners WHERE chat_id=?',(ticket['chat_id'],)).fetchone()
        if not owner or owner['agent_id']!=agent_id:raise ValueError('Gerente não é o dono vigente.')
        if job_id:
            job=db.execute('SELECT supervisor_id FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not job or job['supervisor_id']!=agent_id:raise ValueError('Plano pertence a outro gerente.')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass # Do not log prompts, credentials or headers.
    def do_POST(self):
        try:
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            expected=TOKEN_FILE.read_text().strip()
            if not expected or not hmac.compare_digest(token,expected):
                self.send_error(401);return
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>256*1024: self.send_error(413);return
            data=json.loads(self.rfile.read(length) or '{}')
            if not isinstance(data,dict):raise ValueError('Objeto JSON obrigatório.')
            agent_id=data.get('agent_id')
            if self.path in {'/unhold','/hold','/submit','/approve','/pause','/recover','/repair-integration','/resume','/prepare-project'}:
                require_manager(agent_id,data.get('job_id'))
            if self.path=='/unhold':
                if not agent_id or not core.native_snapshot(agent_id):raise ValueError('Gerente obrigatório.')
                from .operator_hold import clear
                result=clear(data.get('reason'))
            elif self.path=='/hold':
                from .operator_hold import set_hold
                result=set_hold(data.get('reason') or 'Pausa explícita do usuário')
                core.pause()
            elif self.path=='/status':
                result=compact_report(core.report(data['job_id'])) if data.get('job_id') else overview(core.status())
            elif self.path in {'/projects','/prepare-project'}:
                from .projects import inventory,prepare
                if self.path=='/projects':result=inventory()
                else:
                    if not agent_id:raise ValueError('Agente obrigatório.')
                    snapshot=core.native_snapshot(agent_id)
                    if not snapshot:raise ValueError('Agente inexistente.')
                    core.manager_cwd(snapshot['cwd'])
                    result=prepare(data.get('name'))
            elif self.path=='/submit':
                if not agent_id:raise ValueError('Identificador do supervisor obrigatório.')
                snapshot=core.native_snapshot(agent_id)
                if not snapshot:raise ValueError('Supervisor inexistente.')
                result=core.submit(data['plan'],agent_id)
            elif self.path=='/approve':
                if not agent_id or not data.get('message_id'):raise ValueError('Prova de aprovação humana obrigatória.')
                result=core.approve(data['job_id'],data['message_id'],caller_agent_id=agent_id)
            elif self.path=='/pause':
                if not agent_id or not core.native_snapshot(agent_id):raise ValueError('Agente obrigatório.')
                result=core.pause(data.get('job_id'))
            elif self.path=='/models':
                catalog=json.loads((core.STATE/'catalog.json').read_text())
                with core.database() as db: result=select_for_task(catalog,data.get('task',{}),core.history(db))
            elif self.path=='/report': result=compact_report(core.report(data['job_id']))
            elif self.path=='/recover':
                if not agent_id:raise ValueError('Supervisor obrigatório.')
                result=core.recover(data['job_id'],data.get('reason'),data.get('revised_task'),caller_agent_id=agent_id)
            elif self.path=='/repair-integration':
                result=core.repair_integration(data['job_id'],data.get('blocked_task'),data.get('repair_task'),data.get('reason'),caller_agent_id=agent_id)
            elif self.path=='/resume':
                result=core.resume(data['job_id'],data.get('reason'),caller_agent_id=agent_id)
            else:self.send_error(404);return
            payload=core.encoded(result).encode();self.send_response(200)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            if self.path in {'/submit','/approve','/recover','/repair-integration','/resume'}:WAKE.set()
        except Exception as error:
            payload=core.encoded({'error':str(error)}).encode();self.send_response(400)
            self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(payload)

def wait_agent(agent_id):
    started=time.monotonic()
    try:core.bridge('wait',timeout=70,agentId=agent_id,waitTimeoutMs=60000)
    except Exception:pass
    # Initial-idle and connection errors can return immediately. Avoid a busy
    # reconnect loop; this waits locally and never calls an LLM for status.
    elapsed=time.monotonic()-started
    if elapsed<1:time.sleep(1-elapsed)
    WAKE.set()

def refresh_if_needed():
    """Refresh observable quotas without asking a model for its own usage."""
    path=core.STATE/'catalog.json'
    if path.exists() and time.time()-path.stat().st_mtime<300:return
    # Discovery starts provider helpers, so obey the same host resource reserve.
    from .resources import assess_resources
    if not assess_resources()['allowed']:return
    from .catalog import refresh
    refresh()

def recover_supervisor():
    from .supervision import reconcile
    reconcile()


def serve():
    ensure_api_token()
    with core.database():pass # Complete schema initialization before HTTP threads.
    server=ThreadingHTTPServer(('127.0.0.1',6770),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    from concurrent.futures import ThreadPoolExecutor
    from .operator_hold import active as held
    pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='paseo-maintenance')
    futures={};last={};watchers={}
    def safe(name,function):
        try:function()
        except Exception as error:
            with core.database() as db:core.event(db,'maintenance_deferred',{'component':name,'error':str(error)[-1200:]})
    def schedule(name,seconds,function):
        if name in futures and not futures[name].done():return
        if time.monotonic()-last.get(name,0)<seconds:return
        last[name]=time.monotonic();futures[name]=pool.submit(safe,name,function)
    while True:
        if not held():
            from .permissions import supervisors
            schedule('permissions',5,supervisors)
            schedule('catalog',60,refresh_if_needed)
            schedule('supervision',30,recover_supervisor)
            try:core.tick()
            except Exception as error:
                with core.database() as db:core.event(db,'controller_error',{'error':str(error)})
            with core.database() as db:
                active=[r['agent_id'] for r in db.execute("SELECT agent_id FROM tasks WHERE state='running' AND agent_id IS NOT NULL")]
            for agent_id in active:
                if agent_id not in watchers or not watchers[agent_id].is_alive():
                    thread=threading.Thread(target=wait_agent,args=(agent_id,),daemon=True);thread.start();watchers[agent_id]=thread
            watchers={k:v for k,v in watchers.items() if v.is_alive()}
        WAKE.wait(5);WAKE.clear()
