# Paseo NexoISP — implementação em uso

Este repositório registra a instalação personalizada do Paseo no NexoISP, coletada em **30/10/2026**, incluindo as correções aplicadas nesse dia. Serve para revisão por outras IAs, investigação de falhas e evolução do sistema. A origem principal desta cópia é o servidor NexoISP, e não a instalação mais antiga do servidor principal.

O sistema transforma pedidos em planos, delega programação a agentes independentes, revisa as entregas, integra commits e administra concorrência e troca de assinatura quando há evidência de cota esgotada. Há um gerente por chat; o limite configurado é de até dez trabalhadores por chat, sujeito a recursos e admissão.

## Por onde começar a revisão

1. Leia [a arquitetura](docs/ARQUITETURA.md) e [as regras atuais](config/model-limits.json).
2. Examine `orchestrator/core.py`, `supervision.py`, `policy_integration.py` e `policy_runtime.py`.
3. Confira `policy/policy.mjs`, que intercepta a criação e a execução de agentes no daemon.
4. Veja `native/isolated-provider.py`, os adaptadores Grok/Gemini e os plugins em `plugins/`.
5. Consulte [o histórico recente de correções e limites da verificação](docs/REVISAO.md) antes de propor novas alterações.

| Conteúdo | Local |
| --- | --- |
| Controlador, planejamento, fila, integração e revisão | `orchestrator/`, `flow.py` |
| Motores de roteamento, cotas, recursos e admissão | `orchestrator/policy_runtime.py`, `policy_integration.py`, `resources.py`, `local_capacity.py`, `account_broker.py` |
| Adaptadores dos CLIs e comunicação com o daemon | `native/` |
| Política aplicada ao Paseo 0.13.2 | `policy/` |
| Plugins de provedor e exibição de uso Gemini | `plugins/` |
| Configuração coletada, com identificadores e segredos substituídos | `config/` |
| Serviços, scripts de login e runner Docker | `deploy/` |
| Código distribuído do Paseo efetivamente instalado, incluindo alterações locais | `installed-paseo/` |
| Testes existentes na instalação | `tests/` |
| Proveniência e hashes do material coletado | `SOURCE_MANIFEST.json` |

## Política de modelos nesta cópia

| Papel | Principal | Substituição |
| --- | --- | --- |
| Gerente | GPT-6.1 Sol Alto, conta de gerência | Sonnet 5.5 Alto; Astra Médio somente na exceção definida na política |
| Programador | Grok 4.7 Médio | GPT-6.1 Terra Médio, conta exclusiva → Gemini 3.8 Flash Alto, conta lógica 3 → aguardar cota |
| Revisor | Sonnet 5.5 Alto | Sol Alto para implementação Grok/Terra/Gemini; Sol Médio para Sol; alternativa Grok Alto conforme política |

O gerente, o programador e o revisor usam sessões separadas. O Codex programador tem credenciais separadas da conta Codex de gerência/revisão. A conta lógica Gemini 3 corresponde ao provedor `antigravity2` e ao diretório histórico `account2`; esse nome não significa que a conta lógica 2 continua habilitada. O arquivo `config/model-limits.json` é a referência executável completa, inclusive exceções, recuperação de cota e concorrência.

## Estado e reprodução

Esta é uma cópia de código e configuração para revisão, com caminhos reais da instalação `/home/enok/...`. Não é um instalador universal. A coleta e a publicação não retomam os planos pausados nem executam tarefas dos projetos.

Veja [INSTALACAO.md](docs/INSTALACAO.md) para as dependências e a disposição dos arquivos. Bancos SQLite, mensagens dos chats, repositórios de negócios, tokens, chaves SSH e sessões autenticadas não são parte deste repositório. Precisam de backup/restauração próprios; um clone Git não restaura chats ou sessões.

`installed-paseo/` contém JavaScript distribuído e declarações de tipos de pacotes instalados, incluindo a interface web distribuída. Não representa o código TypeScript/React original completo do upstream. Dependências de terceiros em `node_modules`, binários de provedores e caches não são versionados. Consulte [THIRD_PARTY.md](THIRD_PARTY.md).
