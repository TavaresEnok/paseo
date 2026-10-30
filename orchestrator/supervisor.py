from pathlib import Path
import json
from . import core
from .routing import select_for_task

INSTRUCTIONS="Você é o gerente único de desenvolvimento autônomo deste chat. Converse em português. O usuário autorizou trabalhar sem fiscalização intermediária. Siga somente a política atual acima; textos antigos da conversa não definem modelos ou contas.\nSeu diretório inicial é /home/enok/Documentos/projetos; os projetos ficam em suas subpastas. Consulte paseo-flow projects e prepare-project NOME. Use clones de desenvolvimento e worktrees do controlador, preservando os projetos de origem.\nInvestigue o necessário, planeje entregas funcionais, critérios de aceite, escopos de arquivos, verificações essenciais, dependências reais e prioridade. Divida trabalho independente em paralelo até o limite por chat; revisores ocupam vagas próprias. Não crie microtarefas artificiais ou dependências para serializar trabalho independente.\nEnvie o plano JSON por paseo-flow submit .paseo-plan.json. A autorização permanente dispensa confirmação por tarefa ou comando. Nunca crie trabalhadores fora da fila quando houver um plano ativo. A gerência não implementa código: programação e revisão são sessões distintas escolhidas pelo controlador.\nPlanos têm objective, repo e tasks; cada tarefa tem id, objective, depends_on, specialty, difficulty (1..5), priority, acceptance, allowed_files, tests (listas de argumentos), timeout_seconds e max_attempts. Preserve IDs, commits e histórico. Replaneje tarefas pendentes e recupere bloqueios corrigíveis com motivo concreto. Não estenda escopo nem custos sem autorização.\nAo receber eventos, consulte paseo-flow report ID, trate as reprovações com o feedback completo e continue o backlog aprovado. Não faça polling constante nem repita verificações verdes sem motivo novo. O controlador executa verificações essenciais em runners separados, valida escopo, solicita revisão independente e integra somente entregas aprovadas. Faça verificações amplas nos marcos adequados; não pule validações necessárias nem descreva reuso como execução nova.\nMantenha .paseo-context.md curto. Informe entregas, evidências, decisões e impedimentos reais. Nunca atribua espera de recurso, autenticação ou rede à quota sem prova. Consulte perfis e capacidades quando necessário, sem inventar modelos ou saldos.\nSe o usuário mandar parar/pausar, use paseo-flow pause [ID]; pause sem ID estabelece a pausa global persistente. Quando houver NOVO pedido humano explícito para continuar e a pausa global estiver ativa, use paseo-flow unhold --reason 'Pedido explícito do usuário para continuar'; isso só remove a pausa global, preservando os planos. Depois use paseo-flow resume ID --reason para o plano pausado ou recover para tarefa bloqueada. Mudança de quota, configuração ou reboot não é autorização para retomar.\nGerentes têm ferramentas e sudo de host já autorizados. Trabalhadores recebem sua worktree isolada; encaminham necessidades administrativas ao gerente. Preserve credenciais e utilize somente assinaturas sem custo adicional. Não exponha tokens ou chaves no chat.\n"

def management_title(path, fallback, configured, effort):
    """Principal/substitute title on the manager root. Other cwd stay generic.

    Subdirectories count only where MANAGER_ROOT exists. Main keeps the exact DEV match.
    """
    resolved = Path(path).resolve()
    label = ('Gerente substituto — ' if fallback else 'Gerente principal — ') + configured + ' ' + effort
    if resolved == Path(core.DEV).resolve():
        return label
    root = getattr(core, 'MANAGER_ROOT', None)
    if root is not None:
        root = Path(root).resolve()
        if resolved == root or root in resolved.parents:
            return label
    return 'Supervisor autônomo'

def prepare(repo,objective,job_id=None,fallback=False,workspace_id=None,idempotency_key=None):
    path=core.manager_cwd(repo)
    catalog=json.loads((core.STATE/'catalog.json').read_text())
    from .model_limits import load_limits, role_summary
    from .policy_integration import policy_enabled, select_for_role, manager_launch_options, absorb_global
    limits=load_limits()
    if policy_enabled():
        decision=select_for_role(catalog, {'specialty':'planning','supervisor_role':True}, limits,
                                  state=absorb_global({}, catalog, limits))
        if not decision.get('selected'):
            raise RuntimeError('Supervisor permitido indisponível: '+core.encoded(decision.get('rejected')))
        request_key = idempotency_key or f"flow-supervisor-{job_id or core.uid()}-primary"
        chat_id = job_id or str(__import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, request_key))
        db=core.database()
        try:
            if job_id:
                prior = db.execute("SELECT chat_id FROM policy_job_chats WHERE job_id=?", (job_id,)).fetchone()
                if prior: chat_id = prior["chat_id"]
            action, options=manager_launch_options(
                db, chat_id, path, objective, request_key, decision)
        finally:
            db.commit(); db.close()
        options['policyAction']=action
        options.setdefault('labels', {})['flow.logical_primary']='etapa2-supervisor'
        if workspace_id: options['workspaceId']=workspace_id
        return options
    role='fallback' if fallback else 'primary'
    settings=limits.get('supervision',{})
    preferred=[settings[role+'_model']] if settings.get(role+'_model') else [m['provider']+'/'+m['id'] for m in catalog['models'] if
               ('supervisor-fallback' if fallback else 'supervisor') in m.get('roles',[])]
    result=select_for_task(catalog,{'specialty':'planning','difficulty':3,'supervisor_role':role,'allowed_models':preferred})
    if not result['selected']:raise RuntimeError('Supervisor permitido indisponível: '+core.encoded(result['rejected']))
    model=result['selected']
    effort=str(settings.get(role+'_thinking') or model.get('thinking_option_id') or 'medium')
    configured=settings.get(role+'_model') or (model['provider']+'/'+model['id'])
    title=management_title(path, fallback, configured, effort)
    options={
        'provider':model['provider'],'model':model['id'],'modeId':model.get('mode') or 'acceptEdits',
        'thinkingOptionId':model.get('thinking_option_id') or effort,
        'cwd':str(path),'title':title,
        'systemPrompt':role_summary(limits)+'\n\n'+INSTRUCTIONS,'initialPrompt':objective,
        'labels':{'flow.role':'supervisor','flow.supervisor.role':role,'flow.supervisor.thinking':effort,
                  **({'flow.job':job_id} if job_id else {})},
        'idempotencyKey':idempotency_key or f"flow-supervisor-{job_id or core.uid()}-{'fallback' if fallback else 'primary'}"}
    if core.autonomy_policy().get('manager_host_access') is True:
        options['modeId']={'claude':'bypassPermissions','codex':'full-access'}.get(model['provider'],options['modeId'])
    if workspace_id:options['workspaceId']=workspace_id
    if model['provider']=='grok':options.pop('modeId',None)
    if idempotency_key:options['labels']['flow.supervisor.request']=idempotency_key
    return options

def start(repo,objective,job_id=None,fallback=False,workspace_id=None,idempotency_key=None,native_options=None,action=None):
    options=dict(native_options or prepare(repo,objective,job_id,fallback,workspace_id,idempotency_key))
    chosen=action or options.get('policyAction') or ('staged-launch' if options.get('admissionTicket') else 'agent-create')
    agent=core.bridge(chosen,timeout=90,options=options)
    agent_id=core.extract_agent(agent)
    return {'agent_id':agent_id,'provider':options['provider'],'model':options['model'],'repo':options['cwd'],'native':agent}
