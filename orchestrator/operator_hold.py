"""Persistent operator stop. No inference and no clock-based resume."""
import json,os,time,uuid
from pathlib import Path

PATH=Path('/home/enok/srv_projetos/orchestration/OPERATOR-HOLD.json')

def active():
    if not PATH.exists():return False
    try:return json.loads(PATH.read_text()).get('active',True) is not False
    except (OSError,ValueError):return True

def require_running():
    if active():raise RuntimeError('Pausa global explícita do usuário: controlador preservado sem novas execuções. Use paseo-flow unhold --reason após pedido explícito para retomar.')

def set_hold(reason):
    PATH.parent.mkdir(parents=True,exist_ok=True)
    value={'active':True,'reason':reason,'at':time.time()}
    temporary=PATH.with_name(PATH.name+'.'+uuid.uuid4().hex+'.tmp');temporary.write_text(json.dumps(value));temporary.chmod(0o600);temporary.replace(PATH)
    return value

def clear(reason):
    if not str(reason or '').strip():raise ValueError('Motivo explícito obrigatório para remover a pausa global.')
    previous=json.loads(PATH.read_text()) if PATH.exists() else {}
    value={**previous,'active':False,'released_at':time.time(),'release_reason':reason}
    temporary=PATH.with_name(PATH.name+'.'+uuid.uuid4().hex+'.tmp');temporary.write_text(json.dumps(value));temporary.chmod(0o600);temporary.replace(PATH)
    return {'hold':False,'plans_remain_paused':True}
