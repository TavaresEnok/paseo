"""Operator-enforced model and reasoning budgets, shared by routing and catalog."""
import json
from pathlib import Path

LIMITS_FILE=Path('/home/enok/srv_projetos/config/model-limits.json')

def load_limits():
    return json.loads(LIMITS_FILE.read_text())

def allowed_model(provider,model,limits=None):
    limits=limits or load_limits()
    if not isinstance(model,str):return False
    if any(fragment.lower() in model.lower() for fragment in limits['forbidden_model_fragments']):return False
    if provider=='codex-programmer':return bool(limits.get('programmer_account',{}).get('enabled')) and model=='gpt-6.1-terra'
    if provider in {'antigravity','antigravity2','antigravity3'}:
        from .policy_runtime import enabled_gemini
        return provider in enabled_gemini(limits) and model in limits.get('gemini',{}).get('allowed_models',[])
    if provider=='codex':return model in limits['codex']['allowed_models']
    if provider=='opencode' and limits['grok'].get('transport')=='grok-cli':return False
    if provider in {'grok','xai','opencode'}:
        required='grok-'+limits['grok'].get('required_version','4.7')
        return model.rsplit('/',1)[-1].lower()==required and model in limits['grok']['allowed_models']
    return True

def astra_allowed(role, model, effort):
    """Astra stays out of the global allowlist. Only temporary manager medium qualifies."""
    if role != "manager" or effort != "medium" or not isinstance(model, str):
        return False
    return model.lower().rsplit("/", 1)[-1] == "gpt-6-astra"

def constrain_catalog(catalog,task,limits=None):
    limits=limits or load_limits()
    difficulty=task.get('difficulty',3)
    if isinstance(difficulty,str):difficulty={'easy':1,'medium':3,'hard':5}.get(difficulty,3)
    economy=(float(difficulty)<=limits['codex']['economy_max_difficulty'] and
             task.get('specialty') in limits['codex']['economy_specialties'] and task.get('criticality')!='high')
    models=catalog.get('models',[]) if isinstance(catalog,dict) else catalog
    result=[]
    for entry in models:
        model=dict(entry);provider=model.get('provider');model_id=model.get('id')
        if not allowed_model(provider,model_id,limits):
            model['restrictions']={'allowed':False,'notes':'Blocked by explicit user model budget'}
        elif (provider=='claude' and model_id in limits.get('claude',{}).get('frontend_only_models',[]) and
              task.get('specialty')!='frontend'):
            # Declared only by the active policy. An empty or absent list leaves Sonnet selectable.
            model['restrictions']={'allowed':False,'notes':'Sonnet reserved exclusively for frontend by explicit user instruction'}
        elif (provider=='codex' and model_id=='gpt-6.1-sol' and
              limits['codex'].get('sol_complex_only') and
              task.get('specialty')!='review' and
              not sol_matches_supervisor(task,model_id,limits) and
              float(difficulty)<limits['codex'].get('sol_min_difficulty',4)):
            model['restrictions']={'allowed':False,'notes':'Sol reserved for complex tasks by explicit user instruction'}
        elif provider=='grok' or (provider=='opencode' and model_id.startswith('xai/')):
            from .grok_usage import current_evidence,safe_subscription
            if not safe_subscription(current_evidence()):
                model['restrictions']={'allowed':False,'notes':'Fresh subscription-only billing verification is required'}
        elif provider=='codex' and model_id in limits['codex']['economy_models'] and not economy:
            model['restrictions']={'allowed':False,'notes':'Economy models restricted to small research/documentation/utility tasks'}
        result.append(model)
    return {**catalog,'models':result} if isinstance(catalog,dict) else result

def sol_matches_supervisor(task,model_id,limits):
    """Sol may manage at the configured effort for whichever supervision role names it."""
    role=task.get('supervisor_role')
    supervision=limits.get('supervision',{})
    return (role in {'primary','fallback'} and task.get('specialty') in {'planning','coordination'}
            and supervision.get(role+'_model')=='codex/'+model_id)

def role_summary(limits=None):
    """All instructions derive from this structured policy, never a historical chain."""
    limits=limits or load_limits();sup=limits.get('supervision') or {};review=limits.get('review') or {};program=limits.get('programming') or {}
    chain=[(program.get('model'),program.get('thinking_option'))]
    if program.get('fallback_allowed'):
        chain.extend([(program.get('fallback_model'),program.get('fallback_thinking_option')),(program.get('secondary_fallback_model'),program.get('secondary_fallback_thinking_option'))])
    route=' -> '.join(f'{model} ({effort})' for model,effort in chain if model)
    return '\n'.join([
        'POLÍTICA ATUAL GERADA DE model-limits.json. Substitui regras históricas de modelos, esforços e contas.',
        f"Gerente único por chat: {sup.get('primary_model')} ({sup.get('primary_thinking')}); reserva {sup.get('fallback_model')} ({sup.get('fallback_thinking')}).",
        f'Programação em ordem: {route}. Trocar somente após quota esgotada confirmada; transporte/autenticação não são quota. Se todas esgotarem, aguardar renovação.',
        'Codex programador usa conta isolada exclusivamente para programação; não usar a conta de gerência/revisão como programador. Somente Gemini conta 3 (antigravity2) habilitado.',
        f"Revisor principal {review.get('model')} ({review.get('thinking_option')}); Sonnet disponível tem prioridade mesmo sem quota GPT. Sem Sonnet, Sol Alto revisa Grok/Terra/Gemini e Sol Médio revisa Sol. Sem GPT e Sonnet, Grok Alto se disponível. Sessões sempre independentes.",
        'Até 10 trabalhadores por chat além de um gerente, conforme recursos. Conta GPT original em modo GPT-only: quatro programadores e dois revisores compartilhados. A conta Terra dedicada segue o limite por chat e recursos, sem compartilhar a quota original.',
        'Astra somente gerente temporário Médio quando Claude, Grok, a conta Terra dedicada (quando habilitada) e todos os Gemini habilitados esgotarem e Codex estiver disponível. Retorno ao Sol Alto com prova positiva mais nova. Nunca esforço acima de Alto; somente assinaturas sem custo adicional.',
        'O gerente planeja, divide escopos independentes, delega, acompanha revisões e continua o backlog autorizado; não implementa. Retorno ao modelo primário somente em fronteira segura, sem interromper trabalhador saudável.',
        'Pausas explícitas são persistentes. Não retomar por mudança de política, quota ou reboot. Pedido explícito para continuar autoriza unhold e resume do mesmo plano, sem nova confirmação. Preservar histórico e entregas; nunca duplicar executores.',
    ])

def thinking_for(model,task,attempt=0,limits=None):
    limits=limits or load_limits()
    key=model['provider']+'/'+model['id']
    # Review effort is fixed per role. Difficulty, attempt and retries cannot raise it.
    if task.get('specialty')=='review':
        review=limits.get('review') or {}
        if task.get('review_role')=='fallback' and review.get('fallback_model')==key:
            return review.get('fallback_thinking_option') or review.get('thinking_option')
        if key==review.get('model'):
            return review.get('thinking_option')
        if review.get('fallback_allowed') and key==review.get('fallback_model'):
            return review.get('fallback_thinking_option') or review.get('thinking_option')
        return None
    supervision=limits.get('supervision',{})
    role=task.get('supervisor_role')
    if role in {'primary','fallback'} and task.get('specialty') in {'planning','coordination'}:
        if supervision.get(role+'_model')==key:
            return supervision[role+'_thinking']
    claude=limits.get('claude',{})
    if (model['provider']=='claude' and model['id']==claude.get('supervisor_model') and
            task.get('specialty') in {'planning','coordination'}):
        return claude['supervisor_thinking']
    if (model['provider'],model['id']) in {('opencode','xai/grok-4.7'),('grok','grok-4.7')}:
        return limits['grok']['default_thinking']
    if model['provider']=='codex':
        difficulty=task.get('difficulty',3)
        if isinstance(difficulty,str):difficulty={'easy':1,'medium':3,'hard':5}.get(difficulty,3)
        return 'high' if model['id']=='gpt-6.1-sol' and (float(difficulty)>=4 or attempt>=2) else 'medium'
    options=model.get('safe_thinking_options',[])
    difficulty=task.get('difficulty',3)
    if isinstance(difficulty,str):difficulty={'easy':1,'medium':3,'hard':5}.get(difficulty,3)
    if float(difficulty)>=4 and 'high' in options:return 'high'
    for value in ['medium','low','none','off','high','minimal']:
        if value in options:return value
    return None
