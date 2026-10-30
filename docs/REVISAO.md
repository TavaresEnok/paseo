# Contexto para revisão por outras IAs

## Objetivo

Autonomia de desenvolvimento: o usuário fornece uma entrega, um gerente organiza o plano e trabalhadores executam programação/revisão em paralelo. A política limita modelos/esforços, separa credenciais e evita custo adicional fora das assinaturas. A passagem entre provedores por cota não deve perder tentativas, worktrees ou entregas.

## Correções recentes incluídas neste snapshot

- **Atualização posterior à publicação inicial (30/10, 05:29 Fortaleza):** constatado que os campos `developerInstructions` e `config` adicionados pelo adaptador ao `turn/start` não pertencem ao schema `TurnStartParams` do Codex 0.164. A configuração exibida estava atual, mas os dois históricos ainda continham a instrução developer antiga exigindo Grok exclusivo. `installCodexHistoryPolicy` agora usa `thread/inject_items` para acrescentar a política vigente como mensagem developer antes do turno. A atualização ocorre na primeira utilização de cada sessão carregada e quando a política muda; falha da injeção impede iniciar o turno. O histórico é preservado. Os dois rollouts reais registraram a nova mensagem developer, e o gerente Webchat reconheceu a cadeia Terra/Gemini. O instalador verifica agora três pontos de integração, incluindo o adaptador Codex.

- Pausa administrativa persistente e checagem antes do despacho de trabalhadores.
- Operações administrativas da API reservadas ao gerente admitido e atual.
- Chamadas de supervisão ao daemon em segundo plano, evitando segurar a fila durante uma chamada lenta.
- Preservação de tentativa, worktree e feedback na passagem por cota; arquivamento deve ser confirmado antes de liberar a lease ou repetir um lançamento.
- Evidência positiva antiga de cota passa a desconhecida; falhas de transporte/autenticação não são tratadas automaticamente como cota esgotada.
- A conta exclusiva Terra participa da escolha de modo de contingência; sua disponibilidade impede ativar antecipadamente a exceção de gerência Astra.
- Inventário Grok pode responder metadados sem abrir uma sessão de programação nem consumir uma inferência.
- Recuperação de gerência usa a autorização de `manager_cwd`, incluindo o diretório do Webchat.
- Faturamento oficial Grok com saldo zero mantém a evidência de assinatura/configuração válida e indica cota esgotada.
- `integration_owner.py` persiste o responsável da integração antes do merge/runner; uma tarefa recém-pronta não assume o repositório enquanto outra integração ainda valida.
- Resultados de validação permanecem reutilizáveis no mesmo contexto enquanto aguardam confirmação de arquivamento; são encerrados somente após a transição gravada.

As últimas quatro falhas foram reproduzidas em simulações isoladas antes de sua correção. Depois das alterações passaram três reproduções específicas, nove verificações rápidas de política/controle e três testes de recuperação/passagem de cota. Isso não significa que todos os caminhos do sistema ou toda a suíte histórica tenham sido verificados.

## Estado no momento da coleta

O controlador e o daemon estavam ativos. O despacho estava retido pela pausa administrativa solicitada pelo usuário. Havia tarefas concluídas, na fila e bloqueadas; os projetos não foram retomados para criar este repositório. Estado, mensagens, tokens e SQLite de produção não foram exportados.

## Pontos úteis para próxima revisão

1. Compatibilidade entre a política estruturada, filtros legados de roteamento, perfis e mensagens injetadas em sessões já abertas.
2. Recuperação após queda entre gravação SQLite e efeitos no daemon/arquivamento/leases.
3. Propriedade da integração em cancelamento, perda do contexto, restauração de backup e mudança de plano.
4. Validade temporal das provas de quota e comportamento quando a coleta de um provedor falha.
5. Escopo dos caminhos absolutos, comandos de instalação históricos e dependência do broker remoto.
6. Capacidade efetiva por chat versus limite global de recursos e assinaturas compartilhadas.
7. Cobertura dos testes históricos diante da política atual e preparação de um ambiente de testes reproduzível.
8. Relação entre o JavaScript distribuído em `installed-paseo/`, os patches da política e uma futura atualização do upstream.

Sugestões devem citar arquivo e cenário que reproduz a falha. Diferencie problemas confirmados de hipóteses e preserve a pausa explícita do operador durante investigação.

## Economia de contexto e gerência adaptativa — 30/10/2026

A reserva de revisão passa a Sol Médio em todas as implementações. O gerente Sol usa Médio por padrão; o hook de início de turno eleva para Alto em pedido de planejamento complexo, planejamento do próximo lote complexo, conflito de integração ou bloqueio técnico repetido (espera por cota não basta). Volta a Médio quando o gatilho deixa de existir. A escolha ocorre na mesma sessão, é refletida no estado do agente e registrada como `manager_effort_selected` em `policy.jsonl`. A exceção de esforço no ticket é limitada ao papel manager, provedor codex, modelo Sol e valores medium/high. Trabalhadores continuam com esforço fixo no ticket. Erro de leitura do estado usa Alto conservador e registra o erro.

Notificações ordinárias são agrupadas por chat durante 20 segundos; bloqueios seguem imediatamente. A outbox persiste mensagem e UUID para reenvio idempotente, usa steer e descarta notificações de estados substituídos ou pausados. Não cria polling por IA. O pacote de revisão inclui diff limitado, status Git (incluindo arquivos novos), critérios e resultados essenciais; cortes são explícitos e exigem consulta ao conteúdo completo antes da aprovação.

Validação: quatro testes locais de esforço, agrupamento/reenvio, pausa e diff com arquivo novo; verificação isolada de seleção de revisor para Grok/Terra/Gemini/Sol e de limites dos tickets; sintaxe Python/Node. A implantação aguardou todos os agentes ativos terminarem antes de recarregar o daemon. Depois da retomada, duas revisões reais foram admitidas em Sol Médio, uma por projeto. Não houve chamada artificial a modelos para testar.

## Reserva temporária e painel de cotas — 30/10/2026

Com os três programadores regulares comprovadamente esgotados, `codex/gpt-6.1-terra` Médio da conta original pode implementar em sessão independente. Programadores regulares mantêm a rota até esgotamento; a reserva original devolve novas tarefas na primeira recuperação positiva de um regular, respeitando prioridade. Entregas em execução terminam sem interrupção. Espera por autenticação/transporte não autoriza a reserva. A seleção do broker usa o histórico do próprio chat, evitando herdar a rota de outro chat. Limites compartilhados da conta original continuam vigentes.

O plugin de uso existente passou a publicar Codex programador, Grok, Claude e Gemini, junto do Codex original nativo. Grok e Codex usam os coletores oficiais existentes; Claude consulta o endpoint OAuth de uso com a sessão isolada e só mostra erro sanitizado se a consulta falhar. Gemini distingue saldo desconhecido de tokens locais; nenhum percentual é inferido. Reload do plugin sem reiniciar o daemon. Foram confirmados cinco cartões via API do daemon, incluindo janelas reais do Claude; testes isolados cobriram ativação, devolução para os três regulares, permanência dos regulares, evidência desconhecida e espera quando todas as contas esgotam.
