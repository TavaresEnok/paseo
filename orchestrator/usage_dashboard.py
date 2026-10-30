"""Subscription dashboard evidence. Never infer remaining quota from token totals."""
import datetime,json,sqlite3,sys,time,urllib.request,urllib.error
from pathlib import Path
STATE=Path('/home/enok/srv_projetos/orchestration')
def iso(value):
    if isinstance(value,(float,int)):return datetime.datetime.fromtimestamp(value,datetime.timezone.utc).isoformat()
    return value

def unavailable(message):
    return {'status':'unavailable','windows':[],'balances':[],'details':[{'id':'reason','label':'Cota indisponível','value':message}]}

def report(provider):
    try:
        if provider=='codex-programmer':
            from .codex_programmer_usage import evidence_entry
            e=evidence_entry();q=e['quota'];windows=[]
            for w in q['windows']:
                left=w.get('remaining_fraction')
                if left is None:continue
                x={'id':w['id'],'label':'Janela curta' if w['id']=='primary' else 'Semanal','usedPct':round((1-left)*100,2),'remainingPct':round(left*100,2)}
                if w.get('resets_at'):x['resetsAt']=iso(w['resets_at'])
                windows.append(x)
            return {'status':'available','planLabel':'Conta exclusiva de programação','windows':windows,'balances':[],'details':[{'id':'role','label':'Modelo','value':e.get('label','GPT-6.1 Terra — conta nova')},{'id':'observed','label':'Consultado em','value':iso(e['observed_at'])}]}
        if provider=='grok':
            from .grok_usage import refresh,subscription_configuration_safe
            e=refresh();b=e.get('results',{}).get('billing',{})
            if not subscription_configuration_safe(e):return unavailable('Assinatura/cota não confirmada na consulta oficial.')
            left=b['remaining_percent'];w={'id':'subscription','label':'Assinatura','usedPct':100-left,'remainingPct':left}
            if b.get('period_end'):w['resetsAt']=iso(b['period_end'])
            return {'status':'available','planLabel':'SuperGrok','windows':[w],'balances':[],'details':[{'id':'observed','label':'Consultado em','value':e['timestamp_utc']}]}
        if provider=='claude-panel':
            p=Path('/home/enok/srv_projetos/runtime/isolated/claude/home/.claude/.credentials.json')
            auth=json.loads(p.read_text()).get('claudeAiOauth') or {};token=auth.get('accessToken')
            if not token:return unavailable('Credencial OAuth Claude ausente no ambiente isolado.')
            req=urllib.request.Request('https://api.anthropic.com/api/oauth/usage',headers={'Authorization':'Bearer '+token,'anthropic-beta':'oauth-2025-04-20','User-Agent':'paseo-usage-dashboard'})
            with urllib.request.urlopen(req,timeout=10) as response:data=json.load(response)
            windows=[]
            for key,label in [('five_hour','5 horas'),('seven_day','Semanal'),('seven_day_opus','Opus semanal'),('seven_day_sonnet','Sonnet semanal')]:
                v=data.get(key)
                if not isinstance(v,dict) or not isinstance(v.get('utilization'),(int,float)):continue
                used=v['utilization'];w={'id':key,'label':label,'usedPct':used,'remainingPct':max(0,100-used)}
                if v.get('resets_at'):w['resetsAt']=v['resets_at']
                windows.append(w)
            if not windows:return unavailable('Consulta oficial respondeu, mas não informou janelas de cota reconhecidas.')
            return {'status':'available','planLabel':auth.get('subscriptionType') or 'Assinatura Claude','windows':windows,'balances':[],'details':[{'id':'observed','label':'Consultado em','value':iso(time.time())}]}
        if provider=='antigravity2':
            from .gemini_usage import evidence_entry
            e=evidence_entry(account2=True) or {};q=e.get('quota') or {}
            with sqlite3.connect('file:'+str(STATE/'evidence/gemini2-usage.sqlite3')+'?mode=ro',uri=True) as db:
                totals=db.execute('SELECT coalesce(sum(input),0),coalesce(sum(output),0) FROM usage').fetchone()
            status=q.get('status');description='Esgotada; aguardando recuperação confirmada' if status=='exhausted' else 'Última execução concluída; saldo restante não informado' if status=='available' else 'Saldo e disponibilidade não confirmados'
            return {'status':'available','planLabel':'Google — conta 3 · OAuth','windows':[],'balances':[],'details':[{'id':'quota','label':'Cota da assinatura','value':'Saldo não informado pelo CLI'},{'id':'state','label':'Estado confirmado','value':description},{'id':'observed','label':'Última evidência','value':iso(q.get('observed_at')) or 'Sem registro'},{'id':'local','label':'Tokens locais (não é cota)','value':str(sum(totals))}]}
        return unavailable('Provedor desconhecido.')
    except urllib.error.HTTPError as exc:
        return unavailable('Consulta oficial retornou HTTP '+str(exc.code)+(' (sessão OAuth precisa ser renovada).' if exc.code in (401,403) else '.'))
    except Exception as exc:
        return unavailable('Não foi possível consultar: '+type(exc).__name__+'. Tente atualizar; nenhum saldo foi estimado.')

if __name__=='__main__':print(json.dumps(report(sys.argv[1]),ensure_ascii=False))
