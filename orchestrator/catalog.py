"""Build a provenance-preserving registry from native discovery and account usage."""
import json
from pathlib import Path
from . import core
from .model_limits import allowed_model,load_limits

CAPABILITIES=['coding','reasoning','debugging','frontend','backend','long_context','review']
ROLE_SPECIALTIES={
    'supervisor':['coordination','planning'], 'frontend':['frontend'],
    'backend':['backend','coding'], 'avancado':['advanced','debugging','reasoning'],
    'arquiteto':['architecture','reasoning'], 'qa':['review','testing'],
    'auxiliar':['documentation','utility'], 'supervisor-fallback':['coordination','planning'],
    'codex-luna':['research','documentation','utility','formatting','classification'],
    'codex-terra':['research','documentation','utility','formatting','classification'],
    'grok':['backend','coding','research','review','debugging'],
}

def sync_claude_usage_auth(host_home=Path('/home/enok'),runtime_home=Path('/home/enok/srv_projetos/runtime/isolated/claude/home')):
    """Quota discovery uses the host, inference refreshes the isolated account.

    Copy only newer credentials when both local configs identify the same
    account. Never return/log credential data or cross an account change.
    """
    try:
        host_account=json.loads((host_home/'.claude.json').read_text()).get('oauthAccount',{}).get('accountUuid')
        runtime_account=json.loads((runtime_home/'.claude.json').read_text()).get('oauthAccount',{}).get('accountUuid')
        if not host_account or host_account!=runtime_account:return False
        source=runtime_home/'.claude/.credentials.json';dest=host_home/'.claude/.credentials.json'
        src=json.loads(source.read_text());dst=json.loads(dest.read_text())
        if src.get('claudeAiOauth',{}).get('expiresAt',0)<=dst.get('claudeAiOauth',{}).get('expiresAt',0):return False
        temporary=dest.with_name('.credentials.paseo-sync.tmp')
        temporary.write_text(json.dumps(src));temporary.chmod(0o600);temporary.replace(dest)
        return True
    except (OSError,ValueError,TypeError):return False

def build(inventory, usage):
    from .grok_usage import current_evidence,subscription_configuration_safe
    grok_evidence=current_evidence()
    reports={r['sourceId']:r for r in usage.get('reports',[])}
    profiles=inventory.get('profiles',[])
    source_time=inventory['fetchedAt']
    models=[]
    from .gemini_usage import evidence_entry
    gemini=evidence_entry()
    gemini2=evidence_entry(account2=True)
    for provider,catalog in inventory.get('catalogs',{}).items():
        report=reports.get(provider,{})
        account=report.get('report',{})
        windows=[{'id':w.get('id'),'remaining_fraction':w.get('remainingPct',0)/100 if w.get('remainingPct') is not None else None,
                  'resets_at':w.get('resetsAt'),'status':'exhausted' if w.get('remainingPct')==0 else 'known'}
                 for w in account.get('windows',[])]
        extra_disabled=any(d.get('id')=='extra_usage' and str(d.get('value','')).lower()=='disabled' for d in account.get('details',[]))
        credits_zero=any(b.get('id')=='credits' and b.get('remaining')==0 for b in account.get('balances',[]))
        if provider=='codex-programmer':
            from .codex_programmer_usage import evidence_entry as programmer_evidence
            try:models.append(programmer_evidence())
            except Exception as error:
                models.append({'id':'gpt-6.1-terra','provider':'codex-programmer','available':False,'authenticated':False,
                  'cost':{'kind':'unknown','verified':False,'additional_cost':None},
                  'quota':{'status':'unknown','source':'official codex app-server account/rateLimits/read','error':str(error)[:400]},
                  'restrictions':{'allowed':False,'notes':'Quota/auth discovery failed; no positive evidence invented'}})
            continue
        for native in catalog.get('models',[]):
            entry_report=report;entry_account=account;entry_windows=windows
            quota_source='paseo.native.listUsageReports' if report else None
            matching=[p for p in profiles if p.get('provider')==provider and p.get('model')==native['id']]
            roles=[];specialties=[]
            for p in matching:
                role=p.get('id','').removeprefix('etapa2-');roles.append(role);specialties.extend(ROLE_SPECIALTIES.get(role,[]))
            tier='advanced' if any(role in {'avancado','arquiteto','grok'} for role in roles) else 'economy' if any(role in {'auxiliar','codex-luna','codex-terra'} for role in roles) or provider=='opencode' else 'standard'
            # Catalog presence is never sufficient proof of a billable route.
            verified=False;kind='unknown';cost_source=None
            auth=account.get('status')=='available'
            if provider=='claude' and auth and extra_disabled:
                verified=True;kind='subscription';cost_source='native_usage:claude extra_usage=Disabled; isolated OAuth-only runtime'
            elif provider=='codex' and auth and credits_zero:
                verified=True;kind='subscription';cost_source='native_usage:codex ChatGPT quota; credits=0; isolated runtime without API keys'
            elif ((provider=='opencode' and native['id']=='xai/grok-4.7') or (provider=='grok' and native['id']=='grok-4.7')) and subscription_configuration_safe(grok_evidence):
                verified=True;kind='subscription';auth=True
                cost_source='xAI device OAuth + official read-only unified billing: subscription configuration verified, prepaid balance=0, auto-topup disabled'
                entry_report={'fetchedAt':grok_evidence['timestamp_utc']}
                entry_account={'status':'exhausted' if grok_evidence['results']['billing']['remaining_percent']==0 else 'available'}
                billing=grok_evidence['results']['billing']
                entry_windows=[{'id':'weekly','remaining_fraction':billing['remaining_percent']/100,'resets_at':billing['period_end'],'status':'known'}]
                quota_source='official Grok Build read-only billing GET with subscription OAuth'
            if provider in {'antigravity','antigravity2','antigravity3'}:
                gemini=evidence_entry(new2=True) if provider=='antigravity3' else gemini2 if provider=='antigravity2' else evidence_entry()
                if native['id']=='gemini-3.8-flash-high' and gemini:
                    models.append(gemini)
                if provider=='antigravity2' and native['id']=='claude-sonnet-5-5-medium' and (load_limits().get('antigravity_sonnet') or {}).get('enabled'):
                    from .gemini_usage import sonnet_evidence
                    models.append(sonnet_evidence())
                continue
            models.append({
                'id':native['id'],'provider':provider,'label':native.get('label'),'description':native.get('description'),
                'available':bool(catalog.get('models')),'authenticated':auth,'observed_at':source_time,
                'source':'paseo.native.listProviderModels','mode':{'codex':'auto','claude':'acceptEdits','opencode':'build','grok':None,'antigravity':'full-access','antigravity2':'full-access','antigravity3':'full-access'}[provider],
                'safe_thinking_options':[o['id'] for o in native.get('thinkingOptions',[]) if o['id'] in load_limits()['allowed_thinking_options']],
                'context_tokens':native.get('contextWindowMaxTokens'), 'tier':tier,
                'roles':roles,'preferred_specialties':sorted(set(specialties)),
                'role_source':'native agentProfiles (operator preference, not benchmark)',
                'capabilities':{c:{'value':None,'source':None,'confidence':'unknown'} for c in CAPABILITIES},
                'latency_seconds':None,'historical_success_rate':None,
                'cost':{'kind':kind,'verified':verified,'additional_cost':0 if verified else None,'source':cost_source},
                'quota':{'windows':entry_windows,'observed_at':entry_report.get('fetchedAt'),'source':quota_source,
                         'status':entry_account.get('status','unknown'),'session_limit':None,'weekly_limit':None,'monthly_limit':None},
                'restrictions':{'allowed':verified and bool(matching) and allowed_model(provider,native['id']),'notes':'Only configured native profiles and explicit user model limits; unknown billing excluded; capability scores unknown until measured'},
            })
    return {'observed_at':source_time,'source':'native Paseo SDK discovery + usage reports','models':models,
            'benchmarks':{'status':'unknown','notes':'No independently verified numeric benchmark for these exact identifiers was imported.'}}

def refresh():
    from .model_limits import load_limits
    errors={}
    if load_limits()['grok']['allowed_models']:
        from .grok_usage import refresh as refresh_grok
        try:refresh_grok()
        except Exception as error:errors['grok_billing']=str(error)[:500]
    # Usage discovery runs with a private control HOME; user logins stay untouched.
    sync_claude_usage_auth()
    previous_path=core.STATE/'inventory.json'
    try:previous=json.loads(previous_path.read_text()) if previous_path.exists() else {}
    except (OSError,ValueError):previous={}
    try:inventory=core.bridge('inventory',timeout=45)
    except Exception as error:
        errors['inventory']=str(error)[:500];inventory=previous or {'catalogs':{},'profiles':[],'fetchedAt':None}
    for provider,entry in inventory.get('catalogs',{}).items():
        if entry.get('error'):
            errors[provider]=entry['error']
            saved=(previous.get('catalogs') or {}).get(provider) or {}
            if saved.get('models'):inventory['catalogs'][provider]={**saved,'discovery_error':entry['error'],'metadata_reused':True}
    try:usage=core.bridge('usage',timeout=45,refresh=True)
    except Exception as error:
        errors['usage']=str(error)[:500]
        try:usage=json.loads((core.STATE/'usage.json').read_text())
        except (OSError,ValueError):usage={'reports':[]}
    # Isolated account evidence is independent of native provider discovery.
    inventory.setdefault('catalogs',{}).setdefault('codex-programmer',{'models':[]})
    inventory['catalogs'].setdefault('antigravity2',{'models':[{'id':'gemini-3.8-flash-high'}]})
    result=build(inventory,usage)
    result['discovery_errors']=errors
    # Files contain no raw credentials or account identifiers.
    for name,data in [('catalog.json',result),('usage.json',usage),('inventory.json',inventory)]:
        path=core.STATE/name
        temporary=path.with_name(name+'.'+core.uid()+'.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temporary.chmod(0o600)
        temporary.replace(path)
    return {'models':len(result['models']),'zero_cost_allowed':sum(m['cost']['verified'] and m['restrictions']['allowed'] for m in result['models']),'observed_at':result['observed_at']}
