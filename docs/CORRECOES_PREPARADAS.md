# Correções da auditoria — aplicadas no NexoISP

Base: `0bf8b5c`. Branch: `staged/audit-hardening-20261030`.

A preparação foi feita em outra worktree e validada sem alterar os serviços ativos. Em 30/10/2026 o usuário autorizou aplicar e retomar os trabalhos. A implantação preservou worktrees, entregas e contagens de tentativa. Ambos os projetos retomaram com trabalhadores na bridge isolada.

## Comportamento preparado

- **Revisão substituta Sol:** Médio em tarefas comuns; Alto para criticidade elevada, complexidade, autenticação, permissões, segurança, pagamentos, concorrência/fencing, migrations, alterações destrutivas e reprovações anteriores. Examina contrato e nomes de arquivos realmente alterados. O broker recebe o mesmo contexto e assina o esforço exato. Sonnet principal permanece Alto; sessões continuam independentes.
- **Gerência:** complementa palavras do pedido com risco estruturado, inclusive tarefas em andamento/na fila. Uma sessão Sol alterna esforço; nada acima de Alto.
- **Contingência:** preserva a cadeia Grok → Terra dedicado → Gemini 3 → Terra original temporário. Contratos integrados verificam o limite compartilhado e a recuperação de um regular enquanto a reserva ainda trabalha.
- **Notificações:** UUID persistente, backoff e consulta ao recibo receptor. Resposta perdida após recibo completed é reconciliada sem outro envio. Recibo pending sem prova de aceitação vira `needs_attention`, com evento único e verificações espaçadas; não é contornado criando outro UUID. Mensagens antigas/planos pausados são descartados antes da entrega. O estado da tarefa permanece preservado.
- **Recuperações:** orçamento por tarefa de oito falhas automáticas reais ou quatro horas de execução com falha; três falhas equivalentes sem mudança do código interrompem a repetição daquela tarefa. Cota/transporte/slots não consomem esse orçamento. Demais tarefas continuam. Extensão explícita do operador é auditada, sem apagar histórico. Não há estimativa de cobrança monetária a partir desses limites.
- **Autonomia:** root/sudo automático somente para gerente admitido; ferramentas do trabalhador autorizadas dentro da worktree/container. Trabalhadores sem rede do host, credenciais administrativas ou escrita em metadados Git compartilhados. Credenciais da própria assinatura continuam necessárias ao CLI e não são credenciais administrativas do host.
- **Rede:** bridge dedicada `paseo-workers`, comunicação entre containers desativada, IPv6 desligado, bloqueio de host e destinos privados/metadata, saída pública para os provedores. Provisionamento usa a mesma bridge; verificações comuns continuam offline. O instalador de rede imprime o plano por padrão e só executa com `--apply` como root. Requer Docker no backend iptables; divergência é erro de pré-requisito, não queda silenciosa para host networking.
- **CI:** contratos Python/Node e teste real de rede Docker em runner efêmero. Não depende de logins, modelos, Docker do NexoISP ou bancos de produção.

## Evidência e limites

Os contratos locais usam broker HTTP real em loopback, SQLite temporário, seleção do controlador, ticket HMAC e gate JavaScript nativo. O provedor de IA é simulado. Testes do receptor carregam o código distribuído real de MessageReceipts e cobrem concorrência, reinício do receptor e resposta perdida. Isso valida contratos de integração, não latência/cota/respostas dos provedores externos.

O smoke de firewall é exclusivo de runner GitHub efêmero. Não foi executado no servidor dos projetos. Falhas com resultado efetivamente desconhecido não admitem garantia de exactly-once do provedor: quando não há prova, o código preserva a incerteza e exige reconciliação, sem iniciar uma segunda inferência arbitrária.

A classificação de risco continua determinística: nomes e critérios não são prova de segurança. Os testes essenciais, a revisão independente e a possibilidade de ler o contexto completo continuam obrigatórios.

## Aplicação posterior

1. Revisar o diff e os resultados de CI desta branch. Conferir que a instalação ainda corresponde aos hashes da base; se houver mudanças posteriores, portar o patch sem sobrescrevê-las.
2. Preservar configuração autenticada, permissões, bancos e backups do daemon/controlador. **Não copiar a configuração sanitizada inteira do Git para produção.** Aplicar apenas os overlays de política e as alterações revisadas; preservar autorização, logins, identificadores e segredos existentes.
3. Aguardar uma fronteira sem trabalhadores ativos para mudar o runtime do daemon. Preparar bridge/firewall primeiro e verificar o isolamento em ambiente descartável. Configurar reaplicação da política após boot/restart do Docker; o arquivo systemd preparado documenta essa dependência.
4. Aplicar os mesmos módulos de risco/política no controlador e no broker compartilhado. Instalar novos helpers, patch de bridge e política nativa. Mesclar flags de autonomia por papel e de revisão/budget. Não recriar executores, apagar recibos ou retomar planos pausados.
5. Recarregar somente os componentes necessários e confirmar o primeiro lançamento legítimo de revisão Médio/Alto e a continuidade da fila. Em caso de divergência de admissão, restaurar código/configuração do backup; preservar worktrees, commits e bancos.

## Registro da implantação autorizada

Aplicado no NexoISP em 30/10/2026 (14:42–14:45 Fortaleza). O broker compartilhado recebeu os módulos compatíveis; os demais componentes da instalação principal permaneceram na versão anterior. Backup do NexoISP: `/home/enok/.local/state/paseo-backups/audit-activation-20261030T174247Z`.

O host tinha o pool padrão Docker ocupado e não apresentava a chain DOCKER-USER. O instalador agora usa a sub-rede dedicada 172.30.248.0/24, detecta o backend sem mudar alternatives e aplica regras em FORWARD/INPUT/NAT limitadas à própria bridge. Não altera políticas globais nem reinicia Docker. O teste no host confirmou bloqueio de acesso ao host e saída HTTPS para o endpoint OAuth público.

Foi encontrado e corrigido um deadlock existente: `pause()` chamava `_pause()`, ambos serialized, e tentava adquirir flock por um segundo descritor. A exclusão mantém o lock entre processos, mas reaproveita a posse nas chamadas aninhadas da mesma thread. Há regressão executada em subprocesso com timeout.

Os dois trabalhos em curso receberam checkpoints e pausa administrativa. Após reload e confirmação de arquivamento dos executores anteriores, foram retomados pelo controlador nas mesmas worktrees, sem extensão de tentativas. Confirmados programadores ativos nos planos NexoISP `ac5776ea85cb` e Webchat `4e5353155665`, em `paseo-workers`, sem erro nativo no momento da verificação. A recuperação inicial aguardou o carregamento da sessão antiga; não descartou recibos incertos.


## Sonnet trabalhador via Antigravity — aplicado em 30/10/2026

Adicionado `antigravity2/claude-sonnet-5-5-medium` após Gemini e antes de Terra emergencial. Mesmo OAuth, Docker, worktree e bridge; nenhuma nova conta, gerência ou dispatcher. Gemini mantém sua chave histórica de evidência; Sonnet tem chave completa por modelo, SQLite de uso próprio e publicação de esgotamento específica no broker. A consulta oficial `/usage` confirmou grupo Gemini separado do grupo Claude/GPT; ambos os limites do grupo Claude/GPT estavam em 100% na ativação. Esse valor é uma observação do momento, não saldo permanente. Sem coletor periódico novo: execuções atualizam saúde/consumo e a recuperação usa o mecanismo limitado existente.

Wrapper fixa modelo/esforço exatos e recusa créditos Google adicionais. Ticket assinado, gate nativo e runner conferem Flash/High ou Sonnet/Medium; nenhuma elevação autônoma. A revisão de implementação Sonnet prefere Sol quando GPT não está esgotado, em sessão independente; sem GPT preserva revisão Sonnet independente do Claude Code.

Verificação: 23 testes Python locais (incluindo broker HTTP/SQLite, ticket HMAC, gate JS, runner, quota separada, reserva emergencial e revisão adaptativa), sintaxe Python/Node e descoberta no catálogo autenticado. Não houve inferência artificial. A fila foi retida brevemente; a revisão em curso terminou normalmente e todos os agentes estavam ociosos antes do reload. Planos pausados/bloqueados mantiveram seus estados.

Backup remoto: `/home/enok/.local/state/paseo-backups/antigravity-sonnet-20261030T191123Z`. Broker compartilhado atualizado nos mesmos módulos, mantendo leases e banco. A alteração de política pertence ao NexoISP; o daemon do principal não foi alterado.


## Experimento Terra Alto — aplicado em 30/10/2026

Somente a conta dedicada `codex-programmer/gpt-6.1-terra` passa de Médio para Alto, mantendo a prioridade da cadeia. Terra da conta original continua Médio. O roteamento e o broker leem `programmer_account.thinking`; os tickets fixam o esforço exato. Os gates aceitam tickets Medium anteriores para encerrar trabalho já admitido sem elevar esforço nem invalidar sessões em curso, e High para a fase nova. Perfis, catálogo, painel e instruções foram alinhados.

A ferramenta read-only `deploy/worker-comparison.py` registra snapshots em `orchestration/evidence/worker-comparison`: fim de Terra Médio e início de Terra Alto. Inclui evento de corte, contadores de implementação/reprovação/integração por modelo/esforço, tokens de entrada/cache/saída/raciocínio separados por conta e observação de cota existente. Não grava prompts nem credenciais, não chama modelos e não converte tokens em percentuais de assinatura. Tokens cached são subconjunto de entrada e raciocínio é subconjunto da saída. Comparar tarefas semelhantes e excluir entregas herdadas entre fases e bloqueios de ambiente; retrabalho observado não prova causalidade do modelo.

Não há troca automática para Sol: a fase Sol Médio será iniciada em uma mudança posterior. Backup remoto: `/home/enok/.local/state/paseo-backups/terra-high-20261030T204019Z`. O gerente Webchat finalizou o turno após aviso administrativo antes do reload; planos e histórico preservados. Cobertura focada: contrato HTTP broker/tickets, Sonnet independente, roteamento/emergência e contador sem duplicação de cache/raciocínio.
