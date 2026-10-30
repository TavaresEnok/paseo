"""One durable integration owner per repository, across scheduler ticks/restarts."""
from pathlib import Path
import time

def claim(db,task,job):
    db.execute('CREATE TABLE IF NOT EXISTS integration_owners(repo TEXT PRIMARY KEY,job_id TEXT NOT NULL,task_id TEXT NOT NULL,acquired REAL NOT NULL)')
    repo=str(Path(job['repo']).resolve())
    complete_repair(db,repo)
    owner=db.execute('SELECT * FROM integration_owners WHERE repo=?',(repo,)).fetchone()
    if owner:
        previous=db.execute('SELECT state FROM tasks WHERE id=?',(owner['task_id'],)).fetchone()
        if previous and previous['state']=='done':
            db.execute('DELETE FROM integration_owners WHERE repo=?',(repo,));owner=None
        elif owner['job_id']==job['id'] and owner['task_id']==task['id']:
            return True
        else:
            return False # Blocked/paused integrations keep their reviewed ownership.
    from .validation_jobs import pending_integrations
    chosen=None
    for task_id in pending_integrations(repo,job['id']):
        previous=db.execute("SELECT id FROM tasks WHERE id=? AND job_id=? AND state IN ('integrating','blocked','paused')",(task_id,job['id'])).fetchone()
        if previous:chosen=task_id;break
    if chosen is None:
        first=db.execute("SELECT id FROM tasks WHERE job_id=? AND state='integrating' ORDER BY started,id LIMIT 1",(job['id'],)).fetchone()
        chosen=first['id'] if first else task['id']
    db.execute('INSERT INTO integration_owners VALUES(?,?,?,?)',(repo,job['id'],chosen,time.time()))
    db.commit() # Owner is durable BEFORE merge or background runner launch.
    return chosen==task['id']

def release(db,task,job):
    row=db.execute('SELECT state FROM tasks WHERE id=?',(task['id'],)).fetchone()
    if row and row['state']=='done':
        if complete_repair(db,str(Path(job['repo']).resolve())):return
        db.execute('DELETE FROM integration_owners WHERE repo=? AND job_id=? AND task_id=?',(str(Path(job['repo']).resolve()),job['id'],task['id']))
        db.commit()


def initialize_repairs(db):
    db.execute('''CREATE TABLE IF NOT EXISTS integration_repairs(
      repo TEXT PRIMARY KEY,job_id TEXT NOT NULL,blocked_task TEXT NOT NULL,
      repair_task TEXT NOT NULL,reason TEXT NOT NULL,created REAL NOT NULL)''')


def complete_repair(db, repo):
    """Reconcile the done-before-release crash window without losing the owner."""
    initialize_repairs(db)
    row=db.execute('SELECT * FROM integration_repairs WHERE repo=?',(repo,)).fetchone()
    if not row:return False
    repair=db.execute('SELECT state FROM tasks WHERE id=?',(row['repair_task'],)).fetchone()
    if not repair or repair['state']!='done':return False
    job=db.execute('SELECT state FROM jobs WHERE id=?',(row['job_id'],)).fetchone()
    original=db.execute('SELECT state,phase FROM tasks WHERE id=?',(row['blocked_task'],)).fetchone()
    owner=db.execute('SELECT task_id FROM integration_owners WHERE repo=?',(repo,)).fetchone()
    if owner and owner['task_id'] not in {row['repair_task'],row['blocked_task']}:return False
    db.execute('INSERT OR REPLACE INTO integration_owners VALUES(?,?,?,?)',(repo,row['job_id'],row['blocked_task'],time.time()))
    if job and job['state'] in {'running','blocked'} and original and original['state']=='blocked' and original['phase']=='integrate':
        db.execute("UPDATE tasks SET state='integrating',error=NULL,updated=? WHERE id=?",(time.time(),row['blocked_task']))
        db.execute("UPDATE jobs SET state='running',notified=0,updated=? WHERE id=?",(time.time(),row['job_id']))
    from . import core
    core.event(db,'integration_repair_completed',{'repair_task':row['repair_task'],'original_task':row['blocked_task'],'ownership_restored':True},row['job_id'],row['blocked_task'])
    db.execute('DELETE FROM integration_repairs WHERE repo=?',(repo,))
    db.commit()
    return True


def authorize_repair(db, job, original, repair, reason):
    """Explicit handoff to a separately reviewed repair; no arbitrary unlock."""
    from . import core
    from .validation_jobs import context_running
    repo=str(Path(job['repo']).resolve());initialize_repairs(db)
    existing=db.execute('SELECT * FROM integration_repairs WHERE repo=?',(repo,)).fetchone()
    if existing:
        if existing['job_id']==job['id'] and existing['blocked_task']==original['id'] and existing['repair_task']==repair['id']:
            return {'idempotent':True,'repair_task':repair['task_key']}
        raise ValueError('Outra correção de integração já possui a exclusividade.')
    owner=db.execute('SELECT * FROM integration_owners WHERE repo=?',(repo,)).fetchone()
    if not owner or owner['job_id']!=job['id'] or owner['task_id']!=original['id']:
        raise ValueError('A tarefa bloqueada não é a dona atual da integração.')
    if original['id']==repair['id'] or original['job_id']!=job['id'] or repair['job_id']!=job['id']:
        raise ValueError('Correção deve ser tarefa distinta do mesmo plano.')
    if original['state']!='blocked' or original['phase']!='integrate' or repair['state']!='integrating' or repair['phase']!='integrate':
        raise ValueError('Exige integração bloqueada e correção já revisada aguardando integração.')
    if not job['approved'] or job['state'] not in {'running','blocked'}:raise ValueError('Plano aprovado e ativo obrigatório.')
    for task in [original,repair]:
        if context_running({'job':job['id'],'task':task['id'],'phase':'integrate','commit':task['commit_sha']}):
            raise ValueError('Validação ainda executando; não transferir a exclusividade.')
        core.validate_integration_recovery(task,job)
    core.git(job['repo'],'merge-base','--is-ancestor',original['commit_sha'],'HEAD')
    db.execute('INSERT INTO integration_repairs VALUES(?,?,?,?,?,?)',(repo,job['id'],original['id'],repair['id'],reason,time.time()))
    db.execute('UPDATE integration_owners SET task_id=?,acquired=? WHERE repo=?',(repair['id'],time.time(),repo))
    db.execute("UPDATE jobs SET state='running',notified=0,updated=? WHERE id=?",(time.time(),job['id']))
    core.event(db,'integration_repair_authorized',{'original_task':original['id'],'repair_task':repair['id'],'original_commit':original['commit_sha'],'repair_commit':repair['commit_sha'],'reason':reason},job['id'],repair['id'])
    db.commit()
    return {'repair_task':repair['task_key'],'original_task':original['task_key'],'ownership':'repair_until_validated'}
