#!/usr/bin/env python3
"""Explicit operator extension; defaults to a printed plan, no runtime access."""
import argparse,json,os,sys
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('task_id');p.add_argument('--attempts',type=int,default=2);p.add_argument('--reason',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
 if os.getenv('PASEO_AGENT_ID'):raise SystemExit('Execute em um terminal humano, fora de sessão de agente.')
 if not a.apply:print(json.dumps({'task_id':a.task_id,'attempts':a.attempts,'reason':a.reason,'applied':False}));return
 sys.path.insert(0,'/home/enok/.local/share/paseo-orchestrator')
 from orchestrator import core,recovery_budget
 with core.database() as db:recovery_budget.extend(db,a.task_id,a.attempts,a.reason)
 print('Orçamento estendido com auditoria. O plano continua preservado; use recover para a tarefa.')
if __name__=='__main__':main()
