#!/usr/bin/env python3
"""Run workers isolated; authorized manager sessions execute on the host.

This is filesystem/process/resource isolation. Host networking is intentional
for Paseo's authenticated MCP and the local flow API; it is not a network fence.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE = Path('/home/enok/srv_projetos')
RUNTIME = BASE / 'runtime/isolated'
NODE = Path('/home/enok/.local/share/node24')
SOURCE = Path('/home/enok/.local/share/paseo-orchestrator')
ROOTS = [BASE / 'workspace', BASE / 'worktrees']
try:
    if json.loads((BASE/'config/autonomy.json').read_text()).get('unrestricted_tools') is True:
        ROOTS.append(Path('/home/enok/Documentos/projetos'))
except (OSError,ValueError):pass
IMAGE = 'nexoisp-paseo-runtime:20261027'  # node:20 already present; no network pull.
SKILLS = ['paseo', 'paseo-handoff', 'paseo-committee', 'paseo-advisor', 'paseo-help']
ENV_NAMES = [
    'PASEO_AGENT_ID', 'PASEO_AGENT_CWD', 'PASEO_AGENT_PARENT_ID',
    'PASEO_ORCHESTRATOR_URL', 'PASEO_FLOW_URL',
    'PASEO_ROLE_TICKET', 'PASEO_ADMISSION_DB', 'PASEO_CAPACITY_TOKEN_FILE', 'PASEO_FLOW_DB',
    'PASEO_FLOW_CHAT', 'PASEO_FLOW_ROLE', 'PASEO_FLOW_LEASE', 'PASEO_FLOW_PROVIDER',
    'PASEO_TRUSTED_CONTROLLER', 'PASEO_MODEL_LIMITS', 'GROK_REASONING_EFFORT',
    'OPENCODE_CONFIG_CONTENT', 'OPENCODE_DISABLE_AUTOUPDATE', 'OPENCODE_PASSWORD',
    'CLAUDE_AGENT_SDK_VERSION', 'CLAUDE_CODE_ENTRYPOINT',
]

def allowed(path):
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in ROOTS)

def manager_host_cwd(path, root=None):
    """Projects root or a child of it. Path.is_relative_to is not used: the system Python may lack it."""
    path = Path(path).resolve()
    root = Path('/home/enok/Documentos/projetos' if root is None else root).resolve()
    return path == root or root in path.parents

def host_manager_session(provider, requested_cwd, agent_id, autonomy, role=None):
    """Claude/Codex manager on the projects tree. Workers never qualify."""
    return bool(autonomy.get('manager_host_access') is True
                and role not in ('programmer', 'reviewer')
                and provider in ('claude', 'codex')
                and agent_id
                and manager_host_cwd(requested_cwd))

def mount(args, source, target=None, readonly=False):
    if not source.exists():
        return
    spec = f'type=bind,src={source},dst={target or source}'
    if readonly:
        spec += ',readonly'
    destination=str(target or source)
    if any(value.startswith('type=bind,') and ',dst='+destination in value.split(',readonly')[0] and value.split('dst=',1)[1].split(',',1)[0]==destination for value in args):return
    args.extend(['--mount', spec])

def opencode_model_config(raw):
    """Pin foreground and background inference, preserving Paseo's MCP plugins."""
    config = json.loads(raw or '{}')
    config.update(model='xai/grok-4.7', small_model='xai/grok-4.7', enabled_providers=['xai'])
    xai = config.setdefault('provider', {}).setdefault('xai', {})
    xai['whitelist'] = ['grok-4.7']
    model = xai.setdefault('models', {}).setdefault('grok-4.7', {})
    model.setdefault('options', {})['reasoningEffort'] = 'medium'
    agents = config.setdefault('agent', {})
    for name in set(agents) | {'build', 'plan', 'general', 'explore', 'title', 'summary', 'compaction'}:
        agents.setdefault(name, {}).update(model='xai/grok-4.7', variant='medium', reasoningEffort='medium')
    return json.dumps(config)

def _flow_labels(env):
    labels = []
    for env_name, label in (
        ('PASEO_FLOW_CHAT', 'flow.chat'),
        ('PASEO_FLOW_ROLE', 'flow.role'),
        ('PASEO_FLOW_LEASE', 'flow.lease'),
        ('PASEO_FLOW_PROVIDER', 'flow.provider'),
        ('PASEO_TRUSTED_CONTROLLER', 'trustedController'),
    ):
        value = env.get(env_name)
        if value:
            safe = re.sub(r'[^a-zA-Z0-9_.:@/-]', '_', str(value))[:80]
            labels.extend(['--label', f'{label}={safe}'])
    return labels


def hmac_sha(token, payload):
    import hashlib
    import hmac as hmac_mod
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hmac_mod.new(token.encode(), body, hashlib.sha256).hexdigest()


def _grok_turn(args):
    """Model metadata and diagnostics are not a prompt turn and need no ticket."""
    if not args:
        return False
    if args[0] in {'--version', '--help', '-h', 'models', 'metadata', 'model-metadata'}:
        return False
    if 'ModelMetadata' in args or '--model-metadata' in args:
        return False
    return 'agent' in args or '--reasoning-effort' in args


def db_fp(env, ticket):
    import sqlite3
    try:
        db = sqlite3.connect(env.get('PASEO_ADMISSION_DB', ''))
        row = db.execute(
            'SELECT fingerprint FROM current_decisions WHERE chat_id=? AND role=?',
            (ticket.get('chat_id'), ticket.get('role')),
        ).fetchone()
        db.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def apply_grok_admission(provider_args, env=None):
    """Inject the ticket's real --reasoning-effort. A label or env hint is not enough."""
    env = os.environ if env is None else env
    limits_path = env.get('PASEO_MODEL_LIMITS', '/home/enok/srv_projetos/config/model-limits.json')
    try:
        limits = json.loads(Path(limits_path).read_text())
    except (OSError, ValueError):
        limits = {}
    args = list(provider_args)
    if limits.get('policy_engine') != 'proposed-2026-10-29':
        return args
    if any('astra' in str(part).lower() for part in args):
        raise SystemExit('Astra não é um worker Grok.')
    if not _grok_turn(args):
        return args
    import hmac
    import sqlite3
    agent_id = env.get('PASEO_AGENT_ID', '')
    db_path = env.get('PASEO_ADMISSION_DB', '')
    token_path = env.get('PASEO_CAPACITY_TOKEN_FILE', '')
    if not agent_id or not db_path or not token_path:
        raise SystemExit('Admissão Grok ausente: agente, banco ou token.')
    try:
        token = Path(token_path).read_text().strip()
        db = sqlite3.connect(db_path)
        row = db.execute('SELECT ticket_json FROM tickets WHERE agent_id=?', (agent_id,)).fetchone()
        db.close()
    except (OSError, sqlite3.Error) as error:
        raise SystemExit('Admissão Grok ilegível.') from error
    if not row or not row[0]:
        raise SystemExit('Nenhum ticket vinculado a este agent_id.')
    ticket = json.loads(row[0])
    payload = {key: ticket.get(key) for key in (
        'agent_id', 'chat_id', 'cwd', 'decision_fp', 'effort', 'model', 'provider', 'request_id', 'role', 'v')}
    payload['v'] = 1
    if ticket.get('agent_id') and agent_id and ticket.get('agent_id') != agent_id:
        raise SystemExit('Ticket não pertence a este agent_id.')
    mac = hmac_sha(token, payload)
    if not hmac.compare_digest(str(ticket.get('mac') or ''), mac):
        raise SystemExit('Ticket Grok rejeitado.')
    if ticket.get('provider') != 'grok' or ticket.get('model') != 'grok-4.7':
        raise SystemExit('Ticket não é Grok 4.7.')
    role, effort = ticket.get('role'), ticket.get('effort')
    if role == 'programmer' and effort != 'medium':
        raise SystemExit('Programação Grok exige --reasoning-effort medium.')
    if role == 'reviewer' and effort != 'high':
        raise SystemExit('Revisão Grok exige --reasoning-effort high.')
    if role not in {'programmer', 'reviewer'}:
        raise SystemExit('Grok não executa gerência nesta política.')
    flow_path = env.get('PASEO_FLOW_DB') or str(BASE / 'orchestration/state.sqlite3')
    try:
        with sqlite3.connect('file:' + flow_path + '?mode=ro', uri=True) as flow:
            held = flow.execute("SELECT 1 FROM capacity_leases WHERE agent_id=? AND request_id=? AND role=? AND chat_id=? AND status IN ('held','uncertain')",
                                (agent_id, ticket.get('request_id'), ticket.get('role'), ticket.get('chat_id'))).fetchone()
    except sqlite3.Error as error:
        raise SystemExit('Ticket worker sem lease local verificável.') from error
    if not held:
        raise SystemExit('Ticket worker sem lease local held/uncertain vinculada.')
    def pinned_argument(flag, expected):
        found = False
        for index, value in enumerate(args):
            if value == flag:
                found = True
                if index + 1 >= len(args) or args[index + 1] != expected:
                    raise SystemExit('CLI ' + flag + ' não confere com o ticket.')
            elif value.startswith(flag + '='):
                found = True
                if value.split('=', 1)[1] != expected:
                    raise SystemExit('CLI ' + flag + ' não confere com o ticket.')
        if not found:
            args.extend([flag, expected])
    pinned_argument('--model', ticket['model'])
    pinned_argument('--reasoning-effort', effort)
    return args


def assert_cli_admission(provider, provider_args, env=None):
    """Host-side guard before launching any inference CLI (no container DB mounts)."""
    import hmac
    import sqlite3
    env = dict(os.environ if env is None else env)
    if provider == 'grok':
        return  # apply_grok_admission verifies the ticket and exact CLI effort
    if any(arg in ('--version', '--help', 'models') for arg in provider_args):
        return
    limits_path = env.get('PASEO_MODEL_LIMITS') or str(BASE / 'config/model-limits.json')
    limits = json.loads(Path(limits_path).read_text())
    if limits.get('policy_engine') != 'proposed-2026-10-29':
        return
    history_transport=provider in ('codex','codex-programmer') and bool(provider_args) and provider_args[0]=='app-server'
    agent = env.get('PASEO_AGENT_ID')
    if not agent:
        return  # provider discovery has no inference session identity
    try:
        token = Path(env.get('PASEO_CAPACITY_TOKEN_FILE') or BASE / 'config/account-capacity.token').read_text().strip()
        admission = env.get('PASEO_ADMISSION_DB') or str(BASE / 'orchestration/admission.sqlite3')
        with sqlite3.connect('file:' + admission + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT ticket_json FROM tickets WHERE agent_id=?', (agent,)).fetchone()
        ticket = json.loads(row[0]) if row else {}
        payload = {key: ticket.get(key) for key in (
            'agent_id', 'chat_id', 'cwd', 'decision_fp', 'effort', 'model', 'provider', 'request_id', 'role', 'v')}
        payload['v'] = 1
        if not (hmac.compare_digest(str(ticket.get('mac') or ''), hmac_sha(token, payload))
                and ticket.get('agent_id') == agent and ticket.get('provider') == provider):
            raise SystemExit('Ticket CLI inválido.')
        flow_path = env.get('PASEO_FLOW_DB') or str(BASE / 'orchestration/state.sqlite3')
        with sqlite3.connect('file:' + flow_path + '?mode=ro', uri=True) as db:
            if ticket.get('role') in ('programmer', 'reviewer'):
                row = db.execute("SELECT 1 FROM capacity_leases WHERE agent_id=? AND request_id=? AND role=? AND chat_id=? AND status IN ('held','uncertain')",
                                 (agent,ticket['request_id'],ticket['role'],ticket['chat_id'])).fetchone()
                if not row and not history_transport:
                    raise SystemExit('Ticket worker sem lease local held/uncertain vinculada.')
            elif ticket.get('role') == 'manager':
                row = db.execute('SELECT agent_id FROM manager_owners WHERE chat_id=?',(ticket['chat_id'],)).fetchone()
                if not history_transport and (not row or row[0] != agent or db_fp({**env,'PASEO_ADMISSION_DB':admission},ticket) != ticket.get('decision_fp')):
                    raise SystemExit('Gerente CLI não é o dono vigente.')
            else:
                raise SystemExit('Papel CLI inválido.')
        if provider == 'antigravity2' and (ticket.get('role')!='programmer' or ticket.get('model')!='gemini-3.8-flash-high' or ticket.get('effort')!='high'):
            raise SystemExit('Gemini requires programmer / Flash / high.')
        if provider == 'codex-programmer' and (ticket.get('role') != 'programmer' or ticket.get('model') != 'gpt-6.1-terra' or ticket.get('effort') != 'medium'):
            raise SystemExit('Dedicated Codex requires programmer / GPT-6.1 Terra / medium.')
        return ticket.get('role')
    except (OSError, ValueError, sqlite3.Error) as error:
        raise SystemExit('Admissão CLI indisponível.') from error


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ['claude', 'codex', 'codex-programmer', 'opencode', 'grok', 'antigravity2']:
        raise SystemExit('Usage: isolated-provider.py claude|codex|opencode|grok [provider args]')
    provider, provider_args = sys.argv[1], sys.argv[2:]
    admitted_role = assert_cli_admission(provider, provider_args)
    executable_provider = 'codex' if provider == 'codex-programmer' else provider
    executable = Path('/home/enok/.local/bin/agy') if provider=='antigravity2' else NODE/'bin'/executable_provider
    if provider == 'codex-programmer' and os.environ.get('PASEO_AGENT_ID') and admitted_role != 'programmer':
        raise SystemExit('Dedicated Codex account is for programmer sessions only.')
    if provider == 'grok':
        provider_args = apply_grok_admission(provider_args)
    if provider == 'opencode':
        os.environ['OPENCODE_CONFIG_CONTENT'] = opencode_model_config(os.environ.get('OPENCODE_CONFIG_CONTENT'))
    runtime_home = Path('/home/enok/.local/share/paseo-gemini-accounts/account2') if provider=='antigravity2' else RUNTIME / provider / 'home'
    if not runtime_home.is_dir():
        raise SystemExit('Isolated provider runtime has not been initialized.')
    agent_id = os.environ.get('PASEO_AGENT_ID', '')
    requested_cwd = Path(os.environ.get('PASEO_AGENT_CWD') or os.getcwd()).resolve()
    # manager_host_access alone admits a projects subdirectory. unrestricted_tools
    # is what adds that tree to ROOTS for workers; do not treat workers as managers.
    autonomy = json.loads((BASE/'config/autonomy.json').read_text())
    manager_on_host = host_manager_session(provider, requested_cwd, agent_id, autonomy, admitted_role)
    if agent_id and not allowed(requested_cwd) and not manager_on_host:
        raise SystemExit(f'Agent cwd is outside approved development roots: {requested_cwd}')
    cwd = requested_cwd if allowed(requested_cwd) else runtime_home
    # Explicit owner authorization: manager sessions run on the actual host.
    if manager_on_host:
        host_env = dict(os.environ)
        for key in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY',
                    'DEEPSEEK_API_KEY', 'XAI_API_KEY'):
            host_env.pop(key, None)
        host_env.update({
            'HOME': str(runtime_home),
            'CLAUDE_CONFIG_DIR': str(runtime_home / '.claude'),
            'CODEX_HOME': str(runtime_home / '.codex'),
            'XDG_DATA_HOME': str(runtime_home / '.local/share'),
            'XDG_CONFIG_HOME': str(runtime_home / '.config'),
            'XDG_CACHE_HOME': str(runtime_home / '.cache'),
            'PATH': f'{NODE}/bin:{SOURCE}/bin:/home/enok/.local/bin:/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin',
            'PASEO_FLOW_URL': 'http://127.0.0.1:6770',
            'PASEO_MANAGER_HOST_ACCESS': '1',
            'NODE_OPTIONS': '--max-old-space-size=1024',
        })
        os.chdir(requested_cwd)
        os.execve(str(executable), [str(executable), *provider_args], host_env)
    label_id = re.sub(r'[^a-zA-Z0-9_.-]', '_', agent_id or 'discovery')[:80]
    args = [
        '/usr/bin/docker', 'run', '--rm', '--init', '-i',
        '--pull', 'never', '--user', '1000:1000', '--read-only',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--security-opt', 'seccomp=/home/enok/srv_projetos/config/seccomp-default.json',
        '--memory', '2048m' if provider == 'grok' else '1536m', '--memory-swap', '2560m' if provider == 'grok' else '2048m', '--cpus', '1',
        '--pids-limit', '256', '--network', 'host',
        '--label', 'paseo.orchestrator.managed=true',
        '--label', f'paseo.provider={provider}',
        '--label', f'paseo.agent={label_id}',
        *_flow_labels(os.environ),
        '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m,mode=1777',
        '--workdir', str(cwd),
        '--env', f'HOME={runtime_home}',
        '--env','PYTHONDONTWRITEBYTECODE=1','--env','CI=true',
        '--env', f'PATH={NODE}/bin:/home/enok/.local/bin:/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin',
        '--env', 'NODE_OPTIONS=--max-old-space-size=1280' if provider == 'grok' else 'NODE_OPTIONS=--max-old-space-size=1024',
        '--env', f'npm_config_cache={runtime_home}/.cache/npm',
        '--env', f'COREPACK_HOME={runtime_home}/.cache/corepack',
        '--env', f'GOCACHE={runtime_home}/.cache/go-build',
        '--env', f'GOMODCACHE={runtime_home}/.cache/go-mod',
        '--env', f'npm_config_store_dir={runtime_home}/.cache/pnpm-store',
        '--env', 'PASEO_FLOW_URL=http://127.0.0.1:6770',
        '--env', 'GIT_CONFIG_COUNT=1', '--env', 'GIT_CONFIG_KEY_0=safe.directory', '--env', 'GIT_CONFIG_VALUE_0=*',
    ]
    # Only provider state and authorized development paths are writable. No
    # original home, production checkout, Docker socket, daemon credential or DB.
    mount(args, runtime_home)
    # Workers mount their worktree plus required Git metadata.
    if provider == 'grok':
        mount(args, BASE / 'config/grok-requirements.toml', runtime_home / '.grok/requirements.toml', readonly=True)
        args.extend(['--env', f'GROK_HOME={runtime_home}/.grok', '--env', 'GROK_DISABLE_AUTOUPDATER=1',
                     '--env', 'GROK_SUBAGENTS=0', '--env', 'GROK_MEMORY=0', '--env', 'GROK_GOAL=0',
                     '--env', 'GROK_DEFAULT_MODEL=grok-4.7', '--env', 'GROK_WEB_SEARCH_MODEL=grok-4.7'])
    if provider=='antigravity2':mount(args,executable,readonly=True)
    mount(args, NODE, readonly=True)
    mount(args, SOURCE, readonly=True)
    mount(args, Path('/home/enok/.local/bin/paseo-flow'), readonly=True)
    # Workers must not receive the controller's administrative bearer token.
    if provider == 'opencode' and 'serve' in provider_args:
        # Paseo's OpenCode adapter hosts multiple sessions in one HTTP process.
        # It needs the approved development roots; production remains absent.
        for root in ROOTS:
            mount(args, root)
        bridge = BASE / 'runtime/opencode'
        mount(args, bridge, readonly=True)
    elif allowed(cwd):
        if provider == 'claude' and cwd == BASE/'workspace':
            mount(args, BASE/'worktrees', readonly=True)
        mount(args, cwd)
        # A managed worktree points at its original repository's common .git.
        result = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--git-common-dir'], capture_output=True, text=True)
        if result.returncode == 0:
            git_dir = Path(result.stdout.strip())
            git_dir = (git_dir if git_dir.is_absolute() else cwd/git_dir).resolve()
            if not allowed(git_dir):
                raise SystemExit('Git common directory is outside development roots.')
            if git_dir != cwd and cwd not in git_dir.parents:
                mount(args, git_dir)
    for skill in SKILLS:
        source = Path('/home/enok/.agents/skills') / skill
        mount(args, source, runtime_home / '.agents/skills' / skill, readonly=True)
        if provider == 'claude':
            mount(args, source, runtime_home / '.claude/skills' / skill, readonly=True)
    runtime_env = {
        'CLAUDE_CONFIG_DIR': str(runtime_home / '.claude'),
        'CODEX_HOME': str(runtime_home / '.codex'),
        'XDG_DATA_HOME': str(runtime_home / '.local/share'),
        'XDG_CONFIG_HOME': str(runtime_home / '.config'),
        'XDG_CACHE_HOME': str(runtime_home / '.cache'),
    }
    for key, value in runtime_env.items():
        args.extend(['--env', f'{key}={value}'])
    for key in ENV_NAMES:
        if key in os.environ:
            # Pass through by name: never place token-bearing config on argv.
            args.extend(['--env', key])
    # No OPENROUTER_API_KEY, DEEPSEEK_API_KEY, ANTHROPIC_API_KEY or
    # OPENAI_API_KEY is forwarded. Only copied subscription auth is available.
    args.extend([IMAGE, str(executable), *provider_args])
    os.execv(args[0], args)

if __name__ == '__main__':
    main()
