"""Bounded evidence for independent review; full source remains in the worktree."""
import json
import subprocess
from pathlib import Path


def brief(cwd, limit=14000):
    def git(*args):
        # Bound stdout at the pipe; do not allocate a potentially enormous diff.
        with subprocess.Popen(['git','--no-pager','-C',str(cwd),*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as proc:
            data=proc.stdout.read(limit+1)
            if len(data)>limit:
                proc.terminate()
            proc.wait()
        return data[:limit].decode('utf8','replace') + ('\n[Recorte: consultar diff completo na worktree.]' if len(data)>limit else '')
    try:
        status=git('status','--short')
        if len(status)>2500:status=status[:2500]+'\n[Status recortado: execute git status --short para lista completa.]'
        diff=git('diff','--no-ext-diff','--no-textconv','HEAD','--')
        result=Path(cwd)/'.paseo-result.json'
        evidence='Ausente: consultar evidências do controlador antes de aprovar.'
        if result.exists() and result.stat().st_size<=1024*1024:
            value=json.loads(result.read_text())
            # Preserve reported failures; omit verbose logs, not their existence.
            checks=[]
            for check in value.get('tests') or []:
                checks.append({k:check.get(k) for k in ('command','status','exit_code','summary')} if isinstance(check,dict) else str(check)[:500])
            evidence=json.dumps({'status':value.get('status'),'summary':value.get('summary'),'tests':checks,'problems':value.get('problems')},ensure_ascii=False)
            if len(evidence)>5000:evidence=evidence[:5000]+'\n[Recorte: abrir .paseo-result.json completo.]'
        return f'''\nPACOTE INICIAL DE REVISÃO (evidência do executor não substitui revisão independente):
Status Git, incluindo arquivos novos:\n{status}
Diff rastreado:\n{diff}
Resultado essencial:\n{evidence}
Critérios e comandos obrigatórios estão acima. Arquivos ?? são novos e NÃO aparecem no diff: leia-os antes de aprovar. Leia também contexto de código relevante.
Se houver recorte ou dúvida, consulte `git diff --no-ext-diff --no-textconv HEAD --`, os arquivos novos e .paseo-result.json. Logs completos apenas quando necessários; nunca aprove uma parte omitida sem examiná-la.
'''
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        return '\nResumo indisponível ('+type(exc).__name__+'); examine diff, arquivos novos e .paseo-result.json diretamente antes de revisar.\n'
