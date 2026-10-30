# Dependências e reprodução da disposição instalada

Esta documentação descreve o snapshot NexoISP, não executa alterações em servidor algum. Os arquivos mantêm caminhos absolutos usados na instalação. Revise os caminhos e as autorizações antes de usar outro usuário/servidor.

## Base

- Linux, systemd de usuário e Docker.
- Python 3.12 para o controlador; o código usa principalmente a biblioteca padrão.
- Node 24 na instalação do host. O runner Docker usa as versões declaradas em `deploy/runtime/runtime.Dockerfile`.
- Versões dos pacotes CLI coletadas em `config/versions.json`.
- Antigravity CLI instalado separadamente como `~/.local/bin/agy`; o binário não foi copiado.
- Logins próprios das assinaturas Grok, Codex, Claude e Gemini. Nenhuma sessão foi publicada.

## Mapeamento dos arquivos

| Origem neste repositório | Destino NexoISP |
| --- | --- |
| `orchestrator/`, `native/`, `tests/`, `flow.py`, `paseo-flow` | `/home/enok/.local/share/paseo-orchestrator/` |
| `policy/*` | `/home/enok/.local/share/paseo-policy/` |
| Cada diretório `plugins/paseo-*` | Diretório correspondente em `/home/enok/.local/share/` |
| `config/paseo.config.json` | `/home/enok/srv_projetos/config.json` |
| Outros arquivos de `config/`, exceto documentação e `versions.json` | `/home/enok/srv_projetos/config/` |
| `config/workspace/AGENTS.md`, `CLAUDE.md` | `/home/enok/srv_projetos/workspace/` |
| `deploy/systemd/*` | `/home/enok/.config/systemd/user/` |
| `deploy/bin/*` | `/home/enok/.local/bin/` |
| `deploy/runtime/*` | `/home/enok/srv_projetos/install/` |

`deploy/runtime/install.sh` é o script histórico coletado. Ele instala/inicia serviços e cria um workspace; não deve ser tratado como um instalador completo deste repositório. Ele espera que a disposição acima e o Python do host já existam. Tampouco provisiona todos os plugins, contas e dependências novas acrescentadas depois de sua criação.

## Runner Docker

O Dockerfile histórico espera o executável `paseo-compat` no contexto de build. Seu código C está versionado; o binário recompilável foi omitido. Em um ambiente Linux x86_64 com compilador e libc estática, prepare-o antes do build:

```sh
cd deploy/runtime
cc -O2 -static -o paseo-compat paseo-compat.c
docker build -f runtime.Dockerfile -t nexoisp-paseo-runtime:20261027 .
```

Não foi reconstruída a imagem durante a publicação. O filtro C trata a compatibilidade de `clone3` com Docker antigo; não substitui o perfil `config/seccomp-default.json` usado nos comandos do runner.

## Política instalada e código distribuído

Instale as dependências npm nas versões registradas antes de usar `policy/install.py`. Esse aplicador verifica a versão 0.13.2, guarda cópias originais e injeta a política em `agent-manager.js` e no agente Claude. `--check` verifica os hashes registrados no manifesto local da instalação.

`installed-paseo/cli` e `installed-paseo/server` permitem comparar o JavaScript efetivamente instalado, inclusive modificações além dessas duas injeções. Eles não incluem `node_modules`. O instalador de política sozinho não deve ser considerado uma reprodução garantida de todas as diferenças encontradas nesse código distribuído.

## Capacidade compartilhada e segredos

O NexoISP usa `http://127.0.0.1:6771` via túnel para o broker compartilhado. O código do broker está em `orchestrator/account_broker.py`; os exemplos de serviço de origem estão em `deploy/shared-capacity/`. Eles referenciam o servidor principal e precisam de paths, chave SSH e identificadores próprios.

Valores `RECONFIGURE_BEFORE_USE` e `ACCOUNT_ID_RECONFIGURE` precisam ser configurados de modo consistente. Gere o token privado do broker fora do Git, configure o arquivo esperado pelos serviços e realize os logins nos ambientes isolados. O repositório guarda somente referências a esses caminhos.

## Verificações

Os testes em `tests/` são os que existiam no servidor e incluem fixtures históricas. Parte depende de caminhos/versões de política e da disposição instalada. A suíte completa não foi executada durante a publicação. Para executar testes, use uma cópia isolada com os caminhos/configurações ajustados; não aponte uma execução de testes ao SQLite de produção.

O manifesto `SOURCE_MANIFEST.json` identifica os arquivos coletados, seus hashes de origem e os hashes exportados. Arquivos sanitizados são sinalizados. Documentação, exemplos do broker e ferramentas adicionados na preparação da publicação não representam arquivos novos instalados nos servidores.
