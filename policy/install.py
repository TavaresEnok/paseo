#!/usr/bin/env python3
"""Apply a version-pinned, reversible local policy to Paseo 0.13.2."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
CLI = Path('/home/enok/.local/share/node24/lib/node_modules/@getpaseo/cli')
SERVER = CLI / 'node_modules/@getpaseo/server/dist/server/server/agent'
BACKUPS = Path('/home/enok/srv_projetos/config/policy-backups')
NODE = '/home/enok/.local/share/node24/bin/node'
MARKER = '// PASEO_LOCAL_POLICY_V1'
# Declared for a future daemon install. This script does not export them into a live process.
DAEMON_ENV = {
    'PASEO_ADMISSION_DB': '/home/enok/srv_projetos/orchestration/admission.sqlite3',
    'PASEO_CAPACITY_TOKEN_FILE': '/home/enok/srv_projetos/config/account-capacity.token',
    'PASEO_MODEL_LIMITS': '/home/enok/srv_projetos/config/model-limits.json',
    'PASEO_GROK_BILLING': '/home/enok/srv_projetos/orchestration/evidence/grok-billing.json',
    'PASEO_FLOW_DB': '/home/enok/srv_projetos/orchestration/state.sqlite3',
    'PASEO_ACCOUNT_CAPACITY_CONFIG': '/home/enok/srv_projetos/config/account-capacity.json',
}
TARGETS = [
    (SERVER / 'agent-manager.js', 'installManagerPolicy', 'AgentManager'),
    (SERVER / 'providers/claude/agent.js', 'installClaudePolicy', 'ClaudeAgentSession'),
]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    version = json.loads((CLI / 'package.json').read_text())['version']
    if version != '0.13.2':
        raise SystemExit(f'Paseo {version}: revisar compatibilidade antes de aplicar a política.')
    BACKUPS.mkdir(parents=True, exist_ok=True)
    manifest_path = BACKUPS / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if args.check:
        if not manifest or any(digest(Path(path)) != entry['patched_sha256'] for path, entry in manifest.items()):
            raise SystemExit('Política ausente ou arquivos do Paseo alterados; execute install.py e reinicie o daemon.')
        print('Política instalada nos dois pontos do Paseo 0.13.2.')
        return
    # Verify every source before changing any installed file.
    updates = []
    for path, function, cls in TARGETS:
        source = path.read_text()
        backup = BACKUPS / (cls + '.original.js')
        if args.restore:
            if not backup.exists():
                raise SystemExit(f'Backup ausente: {backup}')
            updates.append((path, backup.read_text()))
            continue
        if MARKER in source:
            if str(path) not in manifest or digest(path) != manifest[str(path)]['patched_sha256']:
                raise SystemExit(f'Arquivo já modificado sem checksum válido: {path}')
            continue
        if backup.exists() and source != backup.read_text():
            raise SystemExit(f'Arquivo difere do backup original; revisão necessária: {path}')
        if not backup.exists():
            shutil.copy2(path, backup)
        patched = f"import {{ {function} }} from '{(ROOT / 'policy.mjs').as_uri()}';\n" + source
        patched += f'\n{MARKER}\n{function}({cls});\n'
        updates.append((path, patched))
    for path, source in updates:
        candidate = path.with_suffix('.policy-check.mjs')
        candidate.write_text(source)
        try:
            subprocess.run([NODE, '--check', str(candidate)], check=True)
            candidate.replace(path)
        finally:
            candidate.unlink(missing_ok=True)
        if not args.restore:
            manifest[str(path)] = {'patched_sha256': digest(path)}
    if not args.restore:
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print('Política restaurada.' if args.restore else 'Política aplicada. Reinicie somente o daemon do Paseo para ativar.')

if __name__ == '__main__':
    main()
