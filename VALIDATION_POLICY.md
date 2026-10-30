# Validação proporcional

A validação proporcional é opt-in. Um plano sem `validation_policy` mantém o comportamento anterior do controlador: os checks da tarefa rodam de novo depois da revisão, e cada integração acumula os testes das tarefas já concluídas. Nenhum job existente é reescrito.

```json
"validation_policy": {
  "mode": "proportional_v1",
  "final_tests": [["python3", "-m", "unittest", "tests.test_core"]]
}
```

`mode` precisa ser `proportional_v1`. `final_tests` é uma lista não vazia de comandos, cada um uma lista de argumentos, sem shell. Modo ausente, versão diferente, comandos vazios ou campos desconhecidos rejeitam o plano. `validation_checkpoint` na tarefa, quando presente, é booleano.

No modo optante:

- `tests` da tarefa são os checks essenciais. O controlador os executa depois da implementação. O relato do modelo não substitui essa execução.
- Depois de uma revisão aprovada que não altera o código, o controlador reutiliza essa evidência somente se o digest da fonte, os comandos e o runner continuam iguais e os checks passaram. Evidência ausente, com falha, desatualizada ou ambiente não verificável não autoriza pular: os checks rodam de novo ou o fluxo bloqueia com motivo explícito. Troca da imagem local sob a mesma tag, ou do conteúdo do Node sob o mesmo caminho, muda a identidade e impede o reuso.
- Alteração de código pelo revisor continua reprovada. Check que modifica a fonte continua bloqueado.
- A integração de uma tarefa normal roda os checks dessa tarefa no HEAD combinado. Não soma as suítes das tarefas anteriores. `validation_checkpoint: true` inclui `final_tests` naquela integração. Testes essenciais declarados, inclusive segurança, RLS, concorrência, migração e idempotência, permanecem na tarefa. Não há downgrade automático.
- Quando todas as tarefas estão integradas, `final_tests` roda uma vez no HEAD combinado antes de `job_completed`. A prova guarda HEAD, digest, comandos e a identidade do runner. Essa identidade é o id e os digests da imagem local efetivamente selecionada para os checks, o hash do conteúdo do binário Node montado (runtime do `.nvmrc` quando o arquivo existe, senão o Node padrão, com fallback em `/usr/local/bin/node`) e os parâmetros fixos do runner: rede none, usuário `1000:1000`, somente leitura, `cap-drop ALL` e `pull never`. Tag, caminho ou mtime não autenticam a evidência. Variáveis de ambiente, segredos e caminhos do host ficam de fora. Se a inspeção da imagem ou a leitura do binário falha, o runner fica não verificável e não autoriza reuso nem conclusão. A inspeção é somente leitura, na imagem já presente, sem pull, rede ou alteração do Docker. Ticks seguintes reutilizam essa prova só enquanto ela continuar válida. Falha, árvore suja ou runner não verificável bloqueiam o job, preservam tarefas concluídas, commits e tentativas, e não reabrem implementação.
- O prompt optante pede uma rodada essencial ao fim do bloco e repetição só por falha ou mudança relevante. A revisão lê os resultados já registrados e só pede verificação extra com justificativa técnica. Sucesso guarda comando, status e resumo. Trecho de log fica restrito a falha.
- Eventos e o `result` da tarefa registram a contagem de checks executados e reutilizados. Essa contagem não é percentual de tokens.
