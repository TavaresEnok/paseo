"""Renew subscription OAuth, then verify billing through GETs; no inference."""
import datetime
import importlib.util
import json
import time
from pathlib import Path

SOURCE=Path('/home/enok/.local/share/paseo-orchestrator/native/grok-billing.py')
EVIDENCE=Path('/home/enok/srv_projetos/orchestration/evidence/grok-billing.json')

def current_evidence(max_age_seconds=300,now=None):
    try:
        report=json.loads(EVIDENCE.read_text())
        timestamp=datetime.datetime.fromisoformat(report['timestamp_utc'].replace('Z','+00:00')).timestamp()
        age=(time.time() if now is None else now)-timestamp
        if not 0<=age<=max_age_seconds:return None
        return report
    except (OSError,ValueError,KeyError,TypeError):return None

def subscription_configuration_safe(report):
    if not isinstance(report,dict):return False
    from .model_limits import load_limits
    if load_limits()['grok'].get('transport')=='grok-cli' and report.get('credential_source')!='grok_cli':return False
    billing=report.get('results',{}).get('billing',{})
    topup=report.get('results',{}).get('auto_topup',{})
    remaining=billing.get('remaining_percent')
    return (billing.get('http_status')==200 and billing.get('unified_billing') is True
        and isinstance(remaining,(int,float)) and not isinstance(remaining,bool) and 0<=remaining<=100
        and billing.get('prepaid_cents')==0 and billing.get('on_demand_cap_cents') in (None,0)
        and billing.get('on_demand_enabled') is not True
        and topup.get('http_status')==200 and topup.get('enabled') is False)

def safe_subscription(report):
    return subscription_configuration_safe(report) and report['results']['billing']['remaining_percent']>0


def refresh(force=False):
    existing=current_evidence(60)
    if existing is not None and not force:return existing
    spec=importlib.util.spec_from_file_location('paseo_grok_billing_readonly',SOURCE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.fetch()
    EVIDENCE.parent.mkdir(parents=True,exist_ok=True)
    temporary=EVIDENCE.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');temporary.chmod(0o600);temporary.replace(EVIDENCE)
    return report
