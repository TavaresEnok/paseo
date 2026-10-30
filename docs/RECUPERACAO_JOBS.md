# Recuperação de jobs existentes

Uma tarefa bloqueada não impede o despacho de tarefas independentes do mesmo
job. O job só passa a `blocked` quando não há executor ativo nem tarefa em fila
com todas as dependências concluídas. Falhas de integração consolidada continuam
interrompendo o job, pois podem deixar a branch consolidada com regressão.

Se um executor encerra o turno sem resultado estruturado, o controlador pede uma
continuação na mesma sessão, uma única vez por tentativa/fase, sem gastar outra
tentativa nem ampliar o prazo. Após essa oportunidade, a falha continua sujeita
ao limite original. Não se presume sucesso a partir de um diff existente.

Para corrigir um contrato contraditório e retomar o mesmo job:

```bash
paseo-flow recover JOB --reason 'causa comprovada e correção' --task-spec tarefa-corrigida.json
```

O JSON contém a especificação completa de uma tarefa existente, parada, ainda
em implementação. É possível ampliar os arquivos autorizados, detalhar o
objetivo, acrescentar critérios/testes e ampliar o limite até cinco tentativas
totais. Não é possível remover testes/critérios, mudar dependências/modelos,
alterar tarefa concluída ou em execução, nem zerar tentativas. A recuperação
preserva a worktree e as alterações, o ID do job, sua branch e tarefas prontas.
Os contratos anterior/novo e o motivo ficam registrados no histórico.

Sem `--task-spec`, retoma o trabalho independente e as integrações bloqueadas
de commits já aprovados. Antes de retomar uma integração, verifica a branch de
desenvolvimento, o clone limpo, o commit original, a aprovação independente,
o escopo e a worktree sem novas alterações. Não consome tentativa de programação
nem inicia outro executor/revisor. Não desbloqueia implementações esgotadas.
Jobs pausados não são retomados por essa operação.

O controlador também recupera automaticamente o caso transitório específico
de integração barrada antes do merge porque o clone estava sujo: com autonomia
habilitada, retoma o mesmo commit assim que o clone estiver limpo e as mesmas
verificações de integridade passarem. Conflitos, falhas de testes consolidados,
revisões reprovadas, mudanças no commit e jobs pausados não entram nessa
recuperação automática. Não existe uma repetição irrestrita dos testes.

Arquivos de controle locais na raiz (`.paseo-plan.json`, `.paseo-context.md`,
resultados/revisões e `.paseo-recover[-NOME].json`) são excluídos localmente pelo
Git em `info/exclude`, preservando seu conteúdo. A exclusão não altera o
`.gitignore` do projeto nem encobre mudanças em arquivos rastreados. Arquivos
de código realmente modificados continuam impedindo a integração, e o erro
agora informa seus nomes para o supervisor.

A CLI administrativa local pode executar a recuperação. Pela API privada,
somente o supervisor registrado do próprio job, com autonomia de desenvolvimento
habilitada, pode solicitar a mesma operação. A API não abre acesso ao SQLite.

## Evidência de 27/10/2026

No job `0e8aeab9d2a2`, a verificação do analista exigia `/analista/processos`,
removido anteriormente no commit `e7739b7`. A falha foi reproduzida na branch
base, sem as alterações do menu da gerência; saída em
`evidence/erp-analyst-baseline-20261027.json`.

O contrato da ger-5 passou a incluir a correção dessa única asserção para a
ausência da rota, preservando o menu do analista e os demais testes. As três
tentativas anteriores foram mantidas, com teto ampliado para cinco. Não houve
novo plano nem reexecução da ger-1 já integrada. A ger-2 foi retomada na mesma
worktree, preservando seu diff. Um backup SQLite consistente foi feito antes
da recuperação, na pasta privada `orchestration/backups`.

Validação do controlador: `python3 -m unittest discover -s tests -q`, 96 testes
aprovados. Após recarregar somente `paseo-flow.service`, foram observadas ger-2
e ger-5 em execução pelo Grok 4.7. Isso comprova a retomada, não a conclusão do
ERP. Revisão Sol Baixo, isolamento, limites de modelos e proteções de produção
continuam vigentes.

Na recuperação seguinte, a ger-2 já tinha o commit `1c24fa9` aprovado. Remover
seu arquivo temporário não bastava: o comando antigo retomava o job e deixava
a tarefa em `blocked/integrate`. A operação agora também retoma essa etapa;
o mesmo caso pré-merge passa a ter recuperação automática. As quatro tentativas
foram preservadas. Validação ampliada: 100 testes aprovados, incluindo a
recuperação sem novo agente, proteção de edições reais, respeito à pausa e
recusa de revisões reprovadas/falhas reais de testes.

## Espaço para continuar a fila

Quando a admissão detecta pouco espaço em disco, a manutenção pode remover
somente `node_modules` ignorados pelo Git e caches de testes de worktrees de
tarefas concluídas. Confere que não existe tarefa pendente nem agente nativo
ativo ou ocioso usando aquela worktree. Não limpa clones de integração,
tarefas pausadas, arquivos rastreados ou destinos de symlinks. Código, commits,
resultados e a worktree permanecem disponíveis; dependências podem ser
reinstaladas. Cada remoção fica no evento `completed_dependencies_reclaimed`.

O limite mínimo de espaço não é reduzido. Após a limpeza, o controlador mede
os recursos novamente antes de admitir executores. Na recuperação da ger-2,
foram liberados aproximadamente 5 GiB de dependências/caches das ger-1 e ger-5
concluídas. Validação total: 103 testes aprovados, incluindo preservação de
fonte, dependências rastreadas, symlinks e worktrees ainda em uso.
