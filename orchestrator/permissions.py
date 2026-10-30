"""Approve only routine development actions; protected effects stay pending."""
import re
import shlex
import fnmatch
from pathlib import Path
from . import core

READ_TOOLS={'Read','Glob','Grep','LS','ToolSearch','TodoRead','TodoWrite'}
SAFE_SKILLS={'paseo','paseo-handoff','paseo-committee','paseo-advisor','paseo-help'}
SAFE_PASEO={'list_profiles','list_providers','list_models','inspect_provider','create_workspace','create_agent',
            'list_workspaces','get_workspace','get_agent_status','get_agent_activity','list_agents','get_agent_timeline'}

def safe_command(command,cwd):
    if not isinstance(command,str) or not command.strip():return False
    # Codex checks ancestor instruction files with this fixed read-only loop.
    # Accept that grammar only, never arbitrary shell loops or substitutions.
    instruction_loop=re.compile(r'for\s+(\w+)\s+in\s+([^;]+);\s*do\s+if\s+\[\s+-f\s+"\$\1"\s*\];\s*then\s+cat\s+"\$\1"\s*;\s*fi\s*;\s*done')
    def replace_instruction_loop(match):
        try:paths=shlex.split(match.group(2))
        except ValueError:return match.group(0)
        if paths and all(Path(path).name=='AGENTS.md' and not any(c in path for c in '$`\\\n\r') for path in paths):return 'true'
        return match.group(0)
    command=instruction_loop.sub(replace_instruction_loop,command)
    command=re.sub(r'(?:2>&1|1>&2)(?=\s|$)','',command)
    if any(mark in command for mark in ['`','$(', '${','\r','>','<','\\']):return False
    command=command.replace('\n',';')
    try:
        lexer=shlex.shlex(command,posix=True,punctuation_chars=';&|');lexer.whitespace_split=True;lexer.commenters=''
        tokens=list(lexer)
    except ValueError:return False
    groups=[[]]
    for token in tokens:
        if token in {'&&',';','|'}:groups.append([])
        elif token in {'||','&',';;',';&','|&'}:return False
        else:groups[-1].append(token)
    dangerous={'rm','rmdir','unlink','shred','dd','mkfs','sudo','su','docker','podman','systemctl','service',
               'ssh','scp','curl','wget','kubectl','helm','terraform'}
    for group in groups:
        if not group or group[0] in dangerous:return False
        text=' '.join(group)
        if re.search(r'\b(deploy|publish|billing|payment|truncate)\b|drop\s+(database|table)',text,re.I):return False
        for token in group:
            if token.startswith('/') and not any(Path(token).resolve().is_relative_to(root.resolve()) for root in (core.DEV,core.WORKTREES)):
                return False
            if token.startswith('../') and not Path(cwd,token).resolve().is_relative_to(Path(cwd).resolve()):return False
            if token.startswith('~'):return False
        base=group[0]
        if base=='cd':
            target=group[1:]
            if target[:1]==['--']:target=target[1:]
            if len(target)!=1:return False
            try:cwd=str(core.dev_path(Path(cwd,target[0])))
            except ValueError:return False
            continue
        if group==['true']:continue
        if base in {'pwd','ls','rg','grep','cat','head','tail','wc','which','sort','uniq','cut'}:continue
        if base=='find' and not any(arg in {'-exec','-execdir','-delete','-ok','-okdir','-fprint','-fprintf','-fprint0'} for arg in group):continue
        if base=='git' and len(group)>1 and group[1] in {'status','diff','log','show','rev-parse','ls-files'}:continue
        if base=='git' and group[1:2]==['branch'] and group[2:] in [['-a'],['--all'],['-r'],['--remotes'],['--show-current'],['--list']]:continue
        if base=='paseo-flow' and group[1:]==['--help']:continue
        if base=='paseo-flow' and len(group)>1 and group[1] in {'submit','approve','status','models','report','projects','prepare-project','pause','recover'}:continue
        if base in {'python','python3'} and len(group)>2 and group[1]=='-m' and group[2] in {'unittest','pytest','compileall'}:continue
        if base in {'python','python3','node'} and len(group)>1 and not group[1].startswith('-'):
            script=Path(cwd,group[1]).resolve()
            if script.is_relative_to(Path(cwd).resolve()) and script.is_file():continue
        if base in {'mkdir','touch'} and len(group)>1:continue
        if base=='pytest':continue
        if base=='node' and len(group)>1 and group[1]=='--test':continue
        if base in {'npm','pnpm'} and len(group)>1 and (group[1]=='test' or group[1:3] in [['run','test'],['run','lint'],['run','build'],['run','typecheck'],['run','check']]):continue
        return False
    return True

def authorized_request(snapshot,request):
    from .autonomy import enabled,shell_decision
    if request.get('kind')=='question' or request.get('name') in {'AskUserQuestion','request_user_input'}:return True,'authorized_default_answer'
    if core.autonomy_policy().get('unrestricted_tools') is True:return True,'explicit_user_unrestricted_tools'
    cwd=(request.get('detail') or {}).get('cwd') or (request.get('input') or {}).get('cwd') or snapshot.get('cwd')
    if enabled(cwd):
        if request.get('kind') in {'question','plan','mode'}:return False,'unattended_choose_defaults'
        command=(request.get('detail') or {}).get('command') or (request.get('input') or {}).get('command')
        if isinstance(command,list):command=shlex.join(command)
        if command:return shell_decision(command,cwd)=='allow','standing_unattended_development'
        if request.get('name') in {'Write','Edit','MultiEdit','NotebookEdit','CodexFileChange'}:
            data=request.get('input') or {};path=data.get('file_path') or data.get('path') or data.get('notebook_path')
            if path:
                resolved=Path(cwd,path).resolve()
                if not any(resolved.is_relative_to(root.resolve()) for root in (core.DEV,core.WORKTREES)):return False,'outside_development_roots'
            elif request.get('name')=='CodexFileChange':return False,'scoped_patch_requires_timeline'
        return True,'standing_unattended_development'
    if request.get('kind') in {'question','plan','mode'}:return False,'human_decision_required'
    name=request.get('name','');data=request.get('input') or {};detail=request.get('detail') or {}
    if name in READ_TOOLS:return True,'read_only_discovery'
    if name=='Skill' and data.get('skill') in SAFE_SKILLS:return True,'official_installed_skill'
    if name.startswith('mcp__paseo__') and name.removeprefix('mcp__paseo__') in SAFE_PASEO:return True,'native_managed_orchestration'
    command=detail.get('command') if detail.get('type')=='shell' else data.get('command')
    command=command or data.get('command') or detail.get('command')
    if isinstance(command,list):command=shlex.join(command)
    cwd=detail.get('cwd') or data.get('cwd') or snapshot['cwd']
    try:core.dev_path(cwd)
    except ValueError:return False,'outside_development_roots'
    if command and safe_command(command,cwd):return True,'routine_development_command'
    return False,'protected_or_unclassified_effect'

def approve_routine(snapshot,db=None):
    labels=snapshot.get('labels') or {}
    if not covered_by_autonomy(snapshot):return 0
    count=0
    for request in snapshot.get('pendingPermissions') or []:
        allowed,reason=authorized_request(snapshot,request)
        if not allowed and request.get('name')=='CodexFileChange' and labels.get('flow.task'):
            own_db=db is None
            active_db=db or core.database()
            try:
                task=active_db.execute('SELECT tasks.*,jobs.approved,jobs.state job_state FROM tasks JOIN jobs ON jobs.id=tasks.job_id WHERE tasks.id=?',(labels['flow.task'],)).fetchone()
                if task and task['approved'] and task['job_state']=='running':
                    timeline=core.bridge('timeline',agentId=snapshot['id'],options={'direction':'tail','limit':40,'projection':'canonical'})
                    allowed=authorized_patch(snapshot,request,task,timeline)
                    if allowed:reason='scoped_patch_in_approved_development_plan'
            finally:
                if own_db:active_db.close()
        if not allowed and labels.get('flow.task'):
            command=(request.get('detail') or {}).get('command') or (request.get('input') or {}).get('command') or ''
            if isinstance(command,str) and 'python3 -c' in command and ('.paseo-result.json' in command or '.paseo-review.json' in command):
                core.bridge('permit',agentId=snapshot['id'],requestId=request['id'],response={'behavior':'deny','interrupt':False,
                    'message':'Para gravar o resultado solicitado, use apply_patch/Write somente em .paseo-result.json (ou .paseo-review.json na revisão). O controlador valida o caminho do patch. Não é necessário pedir ao usuário nem encerrar a tarefa.'})
                count+=1
                continue
        if not allowed:
            from .autonomy import enabled
            if enabled(snapshot.get('cwd')):
                core.bridge('permit',agentId=snapshot['id'],requestId=request['id'],response={'behavior':'deny','interrupt':False,
                    'message':'Execução sem supervisão humana autorizada. Não aguarde aceitar/negar. Escolha valores padrão e prossiga no desenvolvimento isolado. Se esta ação estiver fora desse escopo, use alternativa permitida ou registre o impedimento no relatório e continue as outras tarefas.'})
                count+=1
            continue
        response={'behavior':'allow'}
        data=request.get('input') or request.get('detail') or {}
        questions=data.get('questions') or (request.get('detail') or {}).get('questions') or []
        if questions:
            answers={}
            for question in questions:
                key=question.get('question') or question.get('header')
                choices=question.get('options') or []
                first=next((x for x in choices if 'recomend' in str(x).lower()),choices[0] if choices else None)
                answer=(first.get('label') or first.get('value')) if isinstance(first,dict) else first
                if key:answers[key]=str(answer or 'Escolha o padrão adequado ao escopo autorizado e prossiga; preserve a pausa explícita e não amplie custos.')
            if answers:response['updatedInput']={**data,'answers':answers}
        elif request.get('kind')=='question' or request.get('name') in {'AskUserQuestion','request_user_input'}:
            response={'behavior':'deny','interrupt':False,'message':'Sem supervisão intermediária: escolha padrões no escopo aprovado e prossiga. Preserve pausas explícitas.'}
        core.bridge('permit',agentId=snapshot['id'],requestId=request['id'],response=response)
        details={'agent_id':snapshot['id'],'request_id':request['id'],'tool':request.get('name'),'reason':reason}
        if db is not None:core.event(db,'routine_permission_approved',details,labels.get('flow.job'),labels.get('flow.task'))
        else:
            with core.database() as audit_db:core.event(audit_db,'routine_permission_approved',details,labels.get('flow.job'),labels.get('flow.task'))
        count+=1
    return count

def authorized_patch(snapshot,request,task,timeline):
    if timeline.get('projection') not in {'canonical','projected'}:return False
    call_id=(request.get('metadata') or {}).get('itemId')
    if not call_id:return False
    allowed_files=core.decode(task['spec'])['allowed_files']
    metadata_file='.paseo-review.json' if task['phase']=='review' else '.paseo-result.json'
    for entry in timeline.get('entries',[]):
        item=entry.get('item') or {};detail=item.get('detail') or {}
        if item.get('type')!='tool_call' or item.get('callId')!=call_id or item.get('name')!='apply_patch':continue
        if detail.get('type')!='edit' or not isinstance(detail.get('filePath'),str):return False
        path=Path(snapshot['cwd'],detail['filePath']).resolve()
        cwd=Path(snapshot['cwd']).resolve()
        if not path.is_relative_to(cwd):return False
        relative=str(path.relative_to(cwd))
        if '.git' in Path(relative).parts:return False
        return relative==metadata_file or (task['phase']=='implement' and any(fnmatch.fnmatch(relative,p) for p in allowed_files))
    return False

def covered_by_autonomy(snapshot):
    labels=snapshot.get('labels') or {}
    if core.autonomy_policy().get('unrestricted_tools') is True:
        return not snapshot.get('internal') and not snapshot.get('archivedAt') and snapshot.get('provider') in {'claude','codex','codex-programmer','grok','antigravity2'}
    if labels.get('flow.role')=='supervisor' or labels.get('flow.task'):return True
    if core.autonomy_policy().get('auto_approve_development_plans') is not True:return False
    if snapshot.get('internal') or snapshot.get('archivedAt'):return False
    try:core.dev_path(snapshot.get('cwd',''))
    except (ValueError,TypeError):return False
    return snapshot.get('provider') in {'claude','codex','codex-programmer','grok','antigravity2'}

def supervisors():
    from .operator_hold import active as held
    if held():return
    response=core.bridge('agents')
    for entry in response.get('entries',response.get('agents',[])):
        snapshot=entry.get('agent',entry)
        if covered_by_autonomy(snapshot) and not snapshot.get('archivedAt') and snapshot.get('pendingPermissions'):
            try:approve_routine(core.native_snapshot(snapshot['id']))
            except Exception as error:
                with core.database() as db:core.event(db,'permission_handling_deferred',{'agent_id':snapshot['id'],'error':str(error)[-1200:]})
