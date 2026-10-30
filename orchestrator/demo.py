"""Prepare a disposable real-agent acceptance scenario; never touches production."""
from pathlib import Path
from . import core
from .supervisor import start

def setup(name=None):
    repo=core.DEV/(name or ('acceptance-'+core.uid()))
    repo.mkdir(parents=True)
    core.git(repo,'init','-b','main')
    (repo/'tests').mkdir()
    (repo/'.paseo-disposable-demo').write_text('Disposable Paseo acceptance repository.\n')
    (repo/'sum_values.py').write_text('def sum_values(values):\n    raise NotImplementedError\n')
    (repo/'average.py').write_text('def average(values):\n    raise NotImplementedError\n')
    (repo/'summary.py').write_text('def summarize(values):\n    raise NotImplementedError\n')
    (repo/'tests/__init__.py').write_text('')
    (repo/'tests/test_sum.py').write_text('''import unittest
from sum_values import sum_values
class SumTests(unittest.TestCase):
    def test_values(self): self.assertEqual(sum_values([1,2,3]),6)
    def test_negative(self): self.assertEqual(sum_values([-5,2]),-3)
    def test_empty(self): self.assertEqual(sum_values([]),0)
''')
    (repo/'tests/test_average.py').write_text('''import unittest
from average import average
class AverageTests(unittest.TestCase):
    def test_values(self): self.assertEqual(average([2,4,6]),4)
    def test_fraction(self): self.assertAlmostEqual(average([1,2]),1.5)
    def test_empty(self): self.assertIsNone(average([]))
''')
    (repo/'tests/test_summary.py').write_text('''import unittest
from summary import summarize
class SummaryTests(unittest.TestCase):
    def test_values(self): self.assertEqual(summarize([2,4]),{"count":2,"sum":6,"average":3})
    def test_empty(self): self.assertEqual(summarize([]),{"count":0,"sum":0,"average":None})
''')
    (repo/'README.md').write_text('''# Disposable metrics library
Implement sum_values, average (None for empty), and summarize returning count, sum and average.
sum_values and average are independent. summarize should reuse the other two functions.
Do not edit the existing acceptance tests. No dependencies needed beyond Python standard library.
''')
    core.git(repo,'add','--all')
    core.git(repo,'-c','user.name=Paseo Acceptance','-c','user.email=paseo@localhost','commit','-m','Acceptance fixture: intentionally unimplemented metrics')
    exclude=repo/'.git/info/exclude'
    with exclude.open('a') as f:f.write('\n.paseo-plan.json\n.paseo-context.md\n.paseo-result.json\n.paseo-review.json\n__pycache__/\n')
    core.bridge('project-add',cwd=str(repo))
    return str(repo)

def start_acceptance(repo):
    objective='''Demonstração autorizada pelo usuário para validar a Etapa 2 no repositório descartável atual.
Descubra os perfis/provedores nativos, investigue os arquivos e proponha um DAG com pelo menos três tarefas.
Implemente a biblioteca descrita no README usando os testes existentes, com duas tarefas independentes elegíveis para paralelismo.
Não implemente diretamente: escreva .paseo-plan.json e envie à fila persistente com paseo-flow submit.
Use specialty backend para código; não fixe nomes de modelo, deixe o roteador selecionar automaticamente.
Inclua top-level demo:true. Na tarefa que implementa sum_values.py, inclua inject_failure_once:true para o controlador
injetar um defeito proposital de teste APENAS neste repositório descartável e verificar a correção automática.
Os testes por tarefa podem ser python3 -m unittest tests.test_sum, tests.test_average e, na última, discover -s tests.
Não altere testes de aceite. Ao submeter o plano, apresente ID e plano e aguarde aprovação: a autorização de execução
será registrada externamente pelo operador responsável pela demonstração, com a solicitação original do usuário como evidência.
'''
    return start(repo,objective)
