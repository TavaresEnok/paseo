#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

from orchestrator import core
from orchestrator.service import TOKEN_FILE
from orchestrator.routing import select_for_task
from orchestrator.resources import assess_resources

def remote(action,**data):
    data['agent_id']=os.environ.get('PASEO_AGENT_ID')
    request=urllib.request.Request('http://127.0.0.1:6770/'+action,data=core.encoded(data).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN_FILE.read_text().strip()},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=90) as response:return json.load(response)
    except urllib.error.HTTPError as error:raise RuntimeError(error.read().decode())

def main():
    parser=argparse.ArgumentParser(description='Supervisor e fila persistente sobre Paseo.')
    commands=parser.add_subparsers(dest='command',required=True)
    submit=commands.add_parser('submit');submit.add_argument('plan');submit.add_argument('--supervisor')
    approve=commands.add_parser('approve');approve.add_argument('job');approve.add_argument('--message-id');approve.add_argument('--reason')
    status=commands.add_parser('status');status.add_argument('job',nargs='?')
    report=commands.add_parser('report');report.add_argument('job')
    recover=commands.add_parser('recover');recover.add_argument('job');recover.add_argument('--reason',required=True);recover.add_argument('--task-spec')
    models=commands.add_parser('models');models.add_argument('--task',default='{}')
    commands.add_parser('resources');commands.add_parser('tick');commands.add_parser('serve')
    commands.add_parser('refresh-catalog')
    unhold=commands.add_parser('unhold');unhold.add_argument('--reason',required=True)
    commands.add_parser('projects')
    pause=commands.add_parser('pause');pause.add_argument('job',nargs='?')
    resume=commands.add_parser('resume');resume.add_argument('job');resume.add_argument('--reason',required=True)
    prepare=commands.add_parser('prepare-project');prepare.add_argument('name')
    supervisor=commands.add_parser('supervisor');supervisor.add_argument('repo',nargs='?',default=str(core.DEV));supervisor.add_argument('--objective',default='Aguarde o objetivo do usuário. Consulte o catálogo de projetos e siga a autorização permanente de desenvolvimento.')
    clone=commands.add_parser('project');clone.add_argument('source');clone.add_argument('--name',required=True)
    args=parser.parse_args();agent=bool(os.environ.get('PASEO_AGENT_ID'))
    if args.command=='unhold':
        if agent:result=remote('unhold',reason=args.reason)
        else:
            from orchestrator.operator_hold import clear
            result=clear(args.reason)
    elif args.command=='submit':
        plan=json.loads(Path(args.plan).read_text())
        result=remote('submit',plan=plan) if agent else core.submit(plan,args.supervisor)
    elif args.command=='approve':
        result=remote('approve',job_id=args.job,message_id=args.message_id) if agent else core.approve(args.job,args.message_id,args.reason)
    elif args.command=='status':result=remote('status',job_id=args.job) if agent else core.status(args.job)
    elif args.command=='report':result=remote('report',job_id=args.job) if agent else core.report(args.job)
    elif args.command=='recover':
        spec=json.loads(Path(args.task_spec).read_text()) if args.task_spec else None
        result=remote('recover',job_id=args.job,reason=args.reason,revised_task=spec) if agent else core.recover(args.job,args.reason,spec)
    elif args.command=='models':
        task=json.loads(args.task)
        if agent:result=remote('models',task=task)
        else:
            with core.database() as db:result=select_for_task(json.loads((core.STATE/'catalog.json').read_text()),task,core.history(db))
    elif args.command=='resources':result=assess_resources()
    elif args.command=='pause':result=remote('pause',job_id=args.job) if agent else core.pause(args.job)
    elif args.command=='resume':result=remote('resume',job_id=args.job,reason=args.reason) if agent else core.resume(args.job,args.reason)
    elif args.command=='projects':
        from orchestrator.projects import inventory
        result=remote('projects') if agent else inventory()
    elif args.command=='prepare-project':
        from orchestrator.projects import prepare
        result=remote('prepare-project',name=args.name) if agent else prepare(args.name)
    elif agent:raise ValueError('Esta operação administrativa não está disponível aos agentes.')
    elif args.command=='tick':result=core.tick()
    elif args.command=='serve':
        from orchestrator.service import serve
        serve();return
    elif args.command=='refresh-catalog':
        from orchestrator.catalog import refresh
        result=refresh()
    elif args.command=='project':
        import re,subprocess
        if not re.fullmatch('[a-zA-Z0-9_-]+',args.name):raise ValueError('Nome inválido.')
        dest=core.DEV/args.name
        if dest.exists():raise ValueError('Destino já existe.')
        source=Path(args.source).resolve()
        if not source.is_dir():raise ValueError('Use um repositório local existente.')
        subprocess.run(['git','-c','core.hooksPath=/dev/null','clone','--no-hardlinks','--',str(source),str(dest)],check=True,capture_output=True,text=True)
        result=core.bridge('project-add',cwd=str(dest))
    elif args.command=='supervisor':
        from orchestrator.supervisor import start
        result=start(args.repo,args.objective)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
