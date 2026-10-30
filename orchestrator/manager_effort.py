"""Read-only, per-turn Sol manager effort selection. No model calls or mutation."""
import json
import re
import sqlite3


def choose(prompt, jobs, tasks):
    text = str(prompt or '').lower()
    # Explicit planning requests are different from routine progress notifications.
    if re.search(r'(planej\w*|plan\w*|desenh\w*|defin\w*|revis\w*|reestrutur\w*)[^\n.]{0,100}(arquitet|complex|migra[çc]|seguran[çc]|redesign)', text):
        return {'effort': 'high', 'reason': 'complex_planning_request'}
    for task in tasks:
        if task['state'] not in {'blocked', 'launching'}:
            continue
        error = str(task.get('error') or '').lower()
        if re.search(r'(merge.conflict|conflit|integration.owner|integra[çc][aã]o)', error):
            return {'effort':'high', 'reason':'integration_conflict', 'task_id':task['id']}
        # Lack of quota alone is waiting, not a difficult engineering problem.
        if int(task.get('attempt') or 0) >= 2 and not re.search(r'quota|rate.limit|capacity|cota|exhaust', error):
            return {'effort':'high', 'reason':'repeated_technical_block', 'task_id':task['id']}
    if jobs and jobs[0]['state'] == 'done' and 'evento do controlador' in text:
        for task in tasks:
            spec = json.loads(task.get('spec') or '{}')
            difficulty = spec.get('difficulty', 3)
            difficulty = {'easy':1,'medium':3,'hard':5}.get(difficulty,difficulty)
            if float(difficulty) >= 4 or spec.get('criticality') == 'high':
                return {'effort':'high', 'reason':'complex_next_batch_planning', 'job_id':jobs[0]['id']}
    return {'effort':'medium', 'reason':'routine_coordination'}


def select(db_path, agent_id, prompt):
    with sqlite3.connect('file:' + str(db_path) + '?mode=ro', uri=True, timeout=1) as db:
        db.row_factory = sqlite3.Row
        recent = [dict(r) for r in db.execute('SELECT id,state FROM jobs WHERE supervisor_id=? ORDER BY updated DESC LIMIT 50',(agent_id,))]
        mentioned = [j for j in recent if re.search(r'(?<![a-zA-Z0-9])'+re.escape(j['id'])+r'(?![a-zA-Z0-9])', str(prompt or ''))]
        jobs = mentioned or recent[:1]
        tasks = []
        for job in jobs:
            if job['state'] not in {'running','blocked','done'}:
                continue
            tasks += [dict(r) for r in db.execute('SELECT id,state,error,attempt,spec FROM tasks WHERE job_id=?',(job['id'],))]
    return choose(prompt,jobs,tasks)
