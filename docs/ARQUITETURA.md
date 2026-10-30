# Arquitetura da instalação

## Caminho de uma tarefa

O app/web do Paseo conversa com o daemon. Uma sessão de gerente transforma o pedido em plano e usa o controlador HTTP/CLI para administrar esse plano. O controlador persiste tarefas e eventos no SQLite, decide quais tarefas podem rodar juntas, solicita admissão e cria agentes nativos com identidade e papel definidos.

O programador recebe uma worktree e um contrato de arquivos, critérios de aceitação e comandos de validação. A entrega passa por uma sessão independente de revisão. A integração ocorre em uma branch `orchestration/*`, com um responsável persistido por repositório. Resultados de validação são associados ao contexto, digest dos arquivos, comandos e versão do runner. Só são encerrados após a transição persistida de etapa.

## Componentes e responsabilidades

| Componente | Responsabilidade |
| --- | --- |
| `flow.py`, `orchestrator/service.py` | CLI e API do controlador; autenticação e operações administrativas |
| `core.py` | Estados de planos/tarefas, worktrees, execução de verificações, revisão, integração e recuperação |
| `supervision.py`, `supervisor.py`, `supervision_io.py` | Dono da gerência, transições de gerente e chamadas assíncronas ao daemon |
| `policy_runtime.py`, `model_limits.py` | Escolha de modelo/esforço e regras de substituição |
| `catalog.py`, `grok_usage.py`, `gemini_usage.py`, `codex_programmer_usage.py` | Inventário e evidência de autenticação, assinatura e cota |
| `policy_integration.py`, `local_capacity.py`, `account_client.py` | Admissão local/remota, tickets, leases e liberação de capacidade |
| `account_broker.py` | Coordenação da capacidade compartilhada entre servidores/chats |
| `worker_lifecycle.py` | Encerramento/arquivamento com confirmação antes de liberar capacidade |
| `integration_owner.py` | Propriedade persistida da integração, inclusive durante validação em segundo plano |
| `validation.py`, `validation_jobs.py` | Provas de validação, execução em segundo plano e confirmação dos resultados |
| `operator_hold.py` | Pausa administrativa persistente que bloqueia despacho |
| `policy/policy.mjs` | Política aplicada nos pontos de criação/execução de agentes do daemon |
| `native/bridge.mjs`, `staged-launch.mjs` | Ponte Node para o daemon e criação de agentes em etapas |
| `native/isolated-provider.py` | Ambientes e credenciais separados por provedor/papel |
| `plugins/` | Integração de provedores Gemini e painel de uso |

## Diretórios e serviços

- `/home/enok/.local/share/paseo-orchestrator`: fonte própria do controlador, native e testes.
- `/home/enok/.local/share/paseo-policy`: política e aplicação reversível ao Paseo 0.13.2.
- `/home/enok/srv_projetos`: home do daemon, configuração, runtime e estado.
- `/home/enok/Documentos/projetos`: diretório de gerência dos projetos.
- `/home/enok/srv_projetos/workspace` e `worktrees`: clones/cópias de trabalho administrados.
- `paseo-daemon.service`: daemon Node do Paseo.
- `paseo-flow.service`: API e processamento da fila; porta local 6770.
- `paseo-recovery-backup.timer`: backup de recuperação.
- Broker de capacidade: porta local 6771; a instalação atual depende de um broker no servidor principal, acessível por túnel SSH. Os modelos de serviço estão em `deploy/shared-capacity/`.

## Invariantes a preservar

Um gerente por chat. Até dez trabalhadores por chat, sem transformar esse teto em dez compartilhados entre todos os chats. Limites adicionais de recursos/capacidade continuam aplicáveis. Implementação e aprovação em sessões distintas. Substituição de provedor exige evidência de cota; falha de rede ou autenticação deve ser diagnosticada como tal. Pausa explícita não é removida pela recuperação de cota. Uma lease só é liberada depois da confirmação de término/arquivamento do agente correspondente. Uma integração ativa mantém seu responsável até concluir ou ser recuperada.
