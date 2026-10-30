"""Deterministic task risk from structured contracts and changed paths."""
import re
import json

SENSITIVE = re.compile(r'(?:^|[/_.-])(auth(?:entication|orization)?|oauth|mfa|rbac|acl|permissions?|security|crypto|crypt|encrypt|passwords?|tokens?|tenants?|billing|payments?|pagamento|cobran[cç]a|webhook|dispatch|lease|fenc(?:e|ing)|concurren\w*|migration\w*|migracao|migra[cç][aã]o)(?:[/_.-]|$)', re.I)
DESTRUCTIVE = re.compile(r'\b(drop\s+(table|database)|truncate|destructive|destrutiv\w*|irrevers[ií]vel)\b',re.I)

def assess(task=None):
    task=task or {};reasons=[]
    if task.get('criticality') in {'high','critical'}:reasons.append('criticality')
    if task.get('risk') in {'high','critical'}:reasons.append('declared_risk')
    difficulty=task.get('difficulty',3)
    difficulty={'easy':1,'medium':3,'hard':5}.get(difficulty,difficulty)
    try:
        if float(difficulty)>=4:reasons.append('complexity')
    except (TypeError,ValueError):reasons.append('unknown_complexity')
    paths=[*(task.get('allowed_files') or []),*(task.get('changed_files') or [])]
    if any(SENSITIVE.search(str(path)) for path in paths):reasons.append('sensitive_files')
    text=' '.join(str(v) for v in [task.get('objective',''),*(task.get('acceptance') or [])])
    if DESTRUCTIVE.search(text):reasons.append('destructive_change')
    if task.get('review_findings'):reasons.append('previous_review_findings')
    dependencies=task.get('depends_on') or []
    if len(dependencies)>=3 or len(paths)>=12:reasons.append('structural_complexity')
    return {'level':'high' if reasons else 'normal','reasons':reasons}


def review_context(task):
    keys=('objective','acceptance','allowed_files','criticality','risk','difficulty','depends_on','review_findings','changed_files')
    return {k:task[k] for k in keys if k in task}


def previous_review_findings(db,task_id):
    """Implementation completion clears task.error; prior review findings are durable events."""
    for row in db.execute("SELECT data FROM events WHERE task_id=? AND kind IN ('correction_requested','task_blocked')",(task_id,)):
        error=str(json.loads(row[0]).get('error') or '')
        if 'Revisão reprovou' in error or 'Regressão após revisão' in error:return True
    return False
