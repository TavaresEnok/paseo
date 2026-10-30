# Seleção e admissão de tarefas

Os módulos usam somente a biblioteca padrão do Python e não iniciam nem encerram serviços.

## Seleção

```python
from orchestrator.routing import select_model

decision = select_model(catalog, task, history=history, active_models=active, policy=policy)
selected = decision['selected']  # None se não houver candidato elegível
```

`catalog` é um objeto com `models` e, opcionalmente, `observed_at`, ou uma lista de modelos. Cada modelo tem:

- `provider` e `id`: valores descobertos no provedor. A chave canônica é `provider/id`; o ID pode conter barras.
- `available: true`, `authenticated: true`, `observed_at` e `source`.
- `cost: {kind: "subscription" | "free", verified: true, additional_cost: 0, source: "..."}`. Só atribuir `verified` após evidência de que a rota não gera cobrança adicional. OAuth, isoladamente, não é essa evidência.
- `capabilities`: por especialidade, `{value: número entre 0 e 1, source, observed_at, confidence}`. Pontuação sem fonte é desconhecida.
- `context_tokens`, `latency_seconds`, `economy_priority`: opcionais. Prioridade econômica é política do operador, não benchmark.
- `quota`: `{source, observed_at, remaining_fraction, status, resets_at}`; alternativamente `windows` com frações por janela. Uma cota zerada continua bloqueada até atualização, mesmo após o horário previsto de renovação. Leitura positiva vencida vira desconhecida.
- `retry_after`, `max_concurrent`, `restrictions: {allowed: false}`: controles opcionais.

`task` aceita `specialty`, `difficulty` de 1 a 5 (ou easy/medium/hard), `criticality: high`, `required_provider`, `allowed_models`, `excluded_models`, `min_context_tokens`.

`history` mapeia chave do modelo para `{successes, failures, latency_seconds, observed_at}`. `active_models` é um mapa chave → quantidade, ou uma lista de chaves. Candidatos carregados além dos limites ficam inelegíveis. Modelos com falhas anteriores podem ser excluídos em uma nova tentativa; a seleção reavalia apenas as alternativas permitidas.

A resposta informa `selected`, `ranking`, `rejected`, pesos, razões, fontes, idade das evidências e campos onde houve uso do prior. Os pesos padrão são 40% capacidade, 25% sucesso local, 10% latência, 10% cota, 10% distribuição da carga e 5% prioridade econômica. O prior de 0,5 é uma hipótese de decisão declarada, nunca um resultado de benchmark nem saldo estimado.

## Recursos

```python
from orchestrator.resources import sample_resources, assess_resources

sample = sample_resources(previous=previous_sample)
decision = assess_resources(config, active_workers=1, supervisor_active=True, sample=sample)
```

O padrão permite dois trabalhadores e no máximo três agentes totais. Cada nova admissão precisa de 1.024 MiB de reserva do host mais 512 MiB estimados para o novo trabalhador; portanto, 1.536 MiB disponíveis. Bloqueios adicionais consideram CPU, PSI de memória/I/O, atividade de swap e disco. Swap ocupado não é, sozinho, prova de pressão atual; taxa de paginação exige duas amostras.

Não existe ação de interromper produção. Uma admissão negada retorna `action: keep_queued`, com motivos. A primeira amostra informa taxas ainda desconhecidas. Métricas essenciais ausentes ou amostra vencida bloqueiam admissão.

O agendador deve serializar admissões, contabilizar slots antes de iniciar processos e coletar nova amostra. MemAvailable reflete os trabalhadores já residentes; para launches ainda não residentes, o agendador deve manter reserva temporária, evitando que dois lançamentos usem a mesma memória livre observada.

Configuração de referência: `routing-resources.example.json`. Ela não é aplicada automaticamente ao daemon.

## Verificação

```bash
cd /home/app/projects/paseo-orchestrator
python3 -m unittest discover -s tests -p 'test_routing_resources.py' -v
```

São 18 testes de elegibilidade financeira, cotas desconhecidas/vencidas/esgotadas, fallback restrito, especialidade, histórico, limites e pressão de recursos. Os modelos sintéticos existem apenas nos testes.
