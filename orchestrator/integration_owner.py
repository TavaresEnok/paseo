"""One durable integration owner per repository, across scheduler ticks/restarts."""
from pathlib import Path
import time

def claim(db,task,job):
    db.execute('CREATE TABLE IF NOT EXISTS integration_owners(repo TEXT PRIMARY KEY,job_id TEXT NOT NULL,task_id TEXT NOT NULL,acquired REAL NOT NULL)')
    repo=str(Path(job['repo']).resolve())
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
        db.execute('DELETE FROM integration_owners WHERE repo=? AND job_id=? AND task_id=?',(str(Path(job['repo']).resolve()),job['id'],task['id']))
        db.commit()
