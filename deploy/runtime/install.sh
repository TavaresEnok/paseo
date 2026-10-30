#!/bin/bash
set -euo pipefail
NEXO_PY=/home/enok/.local/share/paseo-orchestrator/bin/python3
NEXO_NODE=/home/enok/.local/share/node24
NEXO_BASE=/home/enok/srv_projetos
export PATH="$NEXO_NODE/bin:/home/enok/.local/bin:/usr/local/bin:/usr/bin:/bin"
"$NEXO_PY" - <<'PY'
import shutil
free=shutil.disk_usage('/').free/1024**3
if free<10:raise SystemExit(f'Instalação aguardando espaço: {free:.1f} GiB livres; mínimo de 10 GiB para esta etapa.')
print(f'Espaço disponível: {free:.1f} GiB')
PY
if [ ! -d "$NEXO_NODE/lib/node_modules/@getpaseo/cli" ]; then
"$NEXO_NODE/bin/npm" install --global --prefix "$NEXO_NODE" @getpaseo/cli@0.13.2 @anthropic-ai/claude-code@2.1.310 @openai/codex@0.164.0 @xai-official/grok@1.0.70 corepack@0.36.0 --registry=https://registry.npmjs.org/ --no-audit --no-fund
fi
"$NEXO_NODE/bin/node" --version
"$NEXO_NODE/bin/paseo" --version
"$NEXO_NODE/bin/codex" --version
"$NEXO_NODE/bin/claude" --version
"$NEXO_NODE/bin/grok" --version
docker build --network=host --pull=false -t nexoisp-paseo-runtime:20261027 -f /home/enok/srv_projetos/install/runtime.Dockerfile /home/enok/srv_projetos/install
"$NEXO_PY" /home/enok/.local/share/paseo-policy/install.py
sudo -n loginctl enable-linger enok
systemctl --user daemon-reload
systemctl --user enable --now paseo-daemon.service paseo-flow.service
"$NEXO_PY" - <<'PY'
import sys,json
from pathlib import Path
sys.path.insert(0,'/home/enok/.local/share/paseo-orchestrator')
from orchestrator import core
r=core.bridge('workspace-create',options={'source':{'kind':'directory','path':str(core.DEV)},'title':'workspace','background':False,'idempotencyKey':'nexoisp-principal-workspace-v1'})
p=core.STATE/'evidence/setup-workspace.json';p.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print('Workspace principal criado; serviços independentes ativos; logins próprios ainda necessários.')
PY
systemctl --user is-active paseo-daemon.service paseo-flow.service
df -h /
