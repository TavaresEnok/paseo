#!/usr/bin/env python3
"""Read official Grok billing GET endpoints; emit an allowlisted summary only.

Source: xai-org/grok-build, extensions/billing.rs; login/config.rs;
env/src/lib.rs. Renews existing OAuth when needed; no inference, redirects,
API-key fallback or billing/settings mutations.
"""
import base64
import datetime
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

DB=Path('/home/enok/srv_projetos/runtime/isolated/opencode/home/.local/share/opencode/opencode.db')
SOURCE='https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-shell/src/extensions/billing.rs'
TOKEN_URL='https://auth.x.ai/oauth2/token'
# Public device client also present in the installed OpenCode xAI integration.
CLIENT_ID='b1a00492-073a-47ea-816f-4c329264a828'
CLI_AUTH=Path('/home/enok/srv_projetos/runtime/isolated/grok/home/.grok/auth.json')

def native_cli_oauth(now=None):
    """Let the official CLI maintain its own login; billing only reads its token."""
    now=time.time() if now is None else now
    def read():
        auth=json.loads(CLI_AUTH.read_text())
        entry=auth.get('https://auth.x.ai::'+CLIENT_ID) or auth.get('https://auth.x.ai') or auth.get('https://auth.x.ai/') or auth.get('https://accounts.x.ai/sign-in')
        if not isinstance(entry,dict):raise ValueError('Official CLI subscription login missing')
        access=entry.get('key') or entry.get('access_token')
        if not isinstance(access,str) or len(access.split('.'))!=3:raise ValueError('Subscription OAuth required, never API keys')
        return access,claims(access).get('exp',0)
    access,expires=read()
    if expires<=now+300:
        # Catalog retrieval performs no inference. Only the CLI handles refresh
        # and rotated tokens; never import credentials from OpenCode.
        proc=subprocess.run(['/home/enok/.local/share/paseo-orchestrator/native/isolated-provider.py','grok','models'],capture_output=True,text=True,timeout=40)
        if proc.returncode:raise ValueError('Official CLI login renewal needs attention')
        access,expires=read()
        if expires<=now+60:raise ValueError('Official CLI login is expired')
        status='native_cli_refreshed'
    else:status='valid'
    return {'access':access},{'status':status,'expires_at':expires}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def claims(token):
    part=token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))

def active_credential():
    with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True) as db:
        row=db.execute("SELECT id,value FROM credential WHERE integration_id='xai' AND active=1").fetchone()
    if not row:raise ValueError('No active xAI credential')
    credential=json.loads(row[1])
    if credential.get('type')!='oauth':raise ValueError('Only OAuth is accepted')
    return row[0],row[1],credential

def ensure_oauth(opener=None,now=None):
    """Refresh before the billing admission gate, preserving rotated tokens.

    Local refreshes serialize; a compare-and-swap prevents overwriting a newer
    native OpenCode refresh or an account switch. Tokens never leave the DB or
    the official OAuth request/response in memory.
    """
    now=time.time() if now is None else now
    opener=opener or urllib.request.build_opener(NoRedirect)
    lock_path=DB.with_name('.xai-oauth-refresh.lock')
    with lock_path.open('a') as lock:
        lock_path.chmod(0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        credential_id,raw,credential=active_credential()
        old_claims=claims(credential['access'])
        expires=old_claims.get('exp',0)
        if expires>now+300:return credential,{'status':'valid','expires_at':expires}
        if not credential.get('refresh'):raise ValueError('OAuth refresh credential missing')
        payload=urllib.parse.urlencode({'grant_type':'refresh_token','client_id':CLIENT_ID,'refresh_token':credential['refresh']}).encode()
        request=urllib.request.Request(TOKEN_URL,data=payload,method='POST',headers={
            'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json',
            'User-Agent':'paseo-session-renewal/1.0'})
        try:
            with opener.open(request,timeout=20) as response:tokens=json.load(response)
        except urllib.error.HTTPError as error:
            # Another process may have rotated the token during this request.
            _,latest_raw,latest=active_credential()
            if latest_raw!=raw and claims(latest['access']).get('exp',0)>now+60:
                return latest,{'status':'concurrent_refresh','expires_at':claims(latest['access'])['exp']}
            return credential,{'status':'refresh_failed','http_status':error.code,'reauthentication_may_be_required':error.code in (400,401)}
        access=tokens.get('access_token')
        if not isinstance(access,str) or not access:raise ValueError('OAuth response has no access token')
        new_claims=claims(access)
        if not old_claims.get('sub') or new_claims.get('sub')!=old_claims['sub']:raise ValueError('OAuth account mismatch')
        if new_claims.get('exp',0)<=now+60:raise ValueError('OAuth response already expired')
        refresh=tokens.get('refresh_token') or credential['refresh']
        if not isinstance(refresh,str) or not refresh:raise ValueError('Invalid OAuth refresh token')
        updated={**credential,'access':access,'refresh':refresh,
                 'expires':int(new_claims['exp']*1000)}
        with sqlite3.connect(DB,timeout=30) as db:
            changed=db.execute("UPDATE credential SET value=?,time_updated=? WHERE id=? AND integration_id='xai' AND active=1 AND value=?",
                               (json.dumps(updated),int(now*1000),credential_id,raw)).rowcount
        if not changed:
            _,_,latest=active_credential()
            if claims(latest['access']).get('exp',0)<=now+60:raise ValueError('Concurrent credential update needs retry')
            return latest,{'status':'concurrent_refresh','expires_at':claims(latest['access'])['exp']}
        return updated,{'status':'refreshed','expires_at':new_claims['exp']}

def cents(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Unexpected Cent shape')
    raw=value.get('val',0) # protobuf Cent.val omitted means scalar zero
    if isinstance(raw,bool):raise ValueError('Invalid Cent')
    return int(raw)

def normalize_billing(data):
    config=data.get('config')
    if not isinstance(config,dict):raise ValueError('Missing billing config')
    percent=config.get('creditUsagePercent')
    if not isinstance(percent,(int,float)) or isinstance(percent,bool) or not 0<=percent<=100:
        raise ValueError('Missing or invalid usage percentage')
    period=config.get('currentPeriod') or {}
    return {'used_percent':percent,'remaining_percent':100-percent,
            'period_start':period.get('start'),'period_end':period.get('end'),
            'unified_billing':config.get('isUnifiedBillingUser'),
            'prepaid_cents':cents(config.get('prepaidBalance')),
            'on_demand_cap_present':'onDemandCap' in config,
            'on_demand_cap_cents':cents(config.get('onDemandCap')),
            'on_demand_enabled':data.get('onDemandEnabled')}

def normalize_topup(data):
    rule=data.get('rule')
    if rule is None:
        return {'has_rule':False,'enabled':False,'interpretation':'Official Option<AutoTopupRule>: no configured rule'}
    if not isinstance(rule,dict):raise ValueError('Unexpected auto-topup rule')
    enabled=rule.get('enabled',False) # official serde(default), proto3 false omitted
    if not isinstance(enabled,bool):raise ValueError('Invalid enabled flag')
    return {'has_rule':True,'enabled':enabled,'interpretation':'Official enabled bool defaults false when omitted'}

def fetch():
    report={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'inference_performed':False,'credentials_saved':False,'source':SOURCE,'results':{}}
    try:
        opener=urllib.request.build_opener(NoRedirect)
        transport=json.loads(Path('/home/enok/srv_projetos/config/model-limits.json').read_text()).get('grok',{}).get('transport')
        if transport=='grok-cli':
            credential,auth=native_cli_oauth()
            report['credential_source']='grok_cli'
        else:
            credential,auth=ensure_oauth(opener=opener)
            report['credential_source']='opencode'
        report['authentication']=auth
        report['credentials_saved']=auth['status']=='refreshed'
        if auth['status']=='refresh_failed':
            report['subscription_only_evidence']=False
            return report
        access=credential['access'];subject=claims(access).get('sub')
        if not isinstance(subject,str) or not subject:raise ValueError('Missing subject')
        headers={'Authorization':'Bearer '+access,'X-XAI-Token-Auth':'xai-grok-cli',
                 'x-userid':subject,'x-grok-client-mode':'headless','User-Agent':'paseo-billing-verification/1.0'}
        for name,path,normalize in [('billing','billing?format=credits',normalize_billing),('auto_topup','auto-topup-rule',normalize_topup)]:
            request=urllib.request.Request('https://cli-chat-proxy.grok.com/v1/'+path,headers=headers,method='GET')
            try:
                with opener.open(request,timeout=15) as response:data=json.load(response);status=response.status
                report['results'][name]={'http_status':status,**normalize(data)}
            except urllib.error.HTTPError as error:
                report['results'][name]={'http_status':error.code};break
        billing=report['results'].get('billing',{});topup=report['results'].get('auto_topup',{})
        report['subscription_only_evidence']=(billing.get('http_status')==200 and billing.get('unified_billing') is True
            and billing.get('remaining_percent',0)>0 and billing.get('prepaid_cents')==0
            and topup.get('http_status')==200 and topup.get('enabled') is False
            and billing.get('on_demand_cap_cents') in (None,0) and billing.get('on_demand_enabled') is not True)
    except Exception as error:
        report['error_type']=type(error).__name__;report['subscription_only_evidence']=False
    return report

if __name__=='__main__':
    report=fetch()
    for path in [Path('/home/enok/.local/share/paseo-orchestrator/evidence/grok-billing.json'),Path('/home/enok/srv_projetos/orchestration/evidence/grok-billing.json')]:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
