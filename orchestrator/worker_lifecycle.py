"""One terminal proof before recycling any worker reservation."""
import json,time

def retire(db,task,kind='cancelled',snapshot=None):
    from . import core
    from .policy_integration import policy_enabled,release_task
    task=dict(task);agent=task.get('agent_id')
    if not agent:return True
    proof=core.archive_worker(db,task)
    if not proof:
        core.event(db,'worker_terminal_wait',{'agent_id':agent,'kind':kind},task.get('job_id'),task.get('id'))
        db.commit();return False
    if policy_enabled():release_task(db,task,{'kind':kind,'archive_ack':proof})
    return True

def reconcile_orphans(db):
    from . import core
    from .policy_integration import release_task
    rows=db.execute("""SELECT l.*,t.job_id,t.agent_id AS current_agent,t.state AS task_state
      FROM capacity_leases l LEFT JOIN tasks t ON t.id=l.task_id
      WHERE l.status IN ('held','uncertain')""").fetchall()
    for row in rows:
        # A current active worker is owned by its normal lifecycle path.
        if row['agent_id']==row['current_agent'] and row['task_state'] in ('running','launching','waiting_permission','paused'):continue
        try:snapshot=core.native_snapshot(row['agent_id'])
        except Exception:continue
        # Never infer termination from age, idle, or a missing connection.
        if not isinstance(snapshot,dict) or not snapshot.get('archivedAt'):continue
        task={'id':row['task_id'],'job_id':row['job_id'],'agent_id':row['agent_id']}
        proof={'agent_id':row['agent_id'],'archivedAt':snapshot['archivedAt']}
        release_task(db,task,{'kind':'cancelled','archive_ack':proof})
        core.event(db,'orphan_lease_reconciled',{'lease_id':row['lease_id'],'agent_id':row['agent_id']},row['job_id'],row['task_id'])
    db.commit()

def launch_quota(db,task,options,selection,message):
    """A known native identity makes a startup quota error recoverable safely."""
    from . import core
    from .policy_integration import programmer_quota_handoff,release_task,runtime
    if not runtime().explicit_quota_text(message):return False
    view=dict(task);chosen=selection.get('selected') or {}
    view['agent_id']=options.get('agentId')
    view['selection']=core.encoded(selection)
    view['review_model' if view['phase']=='review' else 'model']=chosen.get('key')
    if not view['agent_id']:return False
    try:snapshot=core.native_snapshot(view['agent_id'])
    except Exception:return False
    if isinstance(snapshot,dict) and snapshot.get('id'):
        if core._snapshot_busy(snapshot):return False
        if not retire(db,view):return False
    elif snapshot is None:
        release_task(db,view,{'kind':'cancelled','native_absent':True,'confirmed':True})
    else:return False
    # Record the model actually selected, including before create returned.
    db.execute('UPDATE tasks SET model=CASE WHEN phase=\'implement\' THEN ? ELSE model END, review_model=CASE WHEN phase=\'review\' THEN ? ELSE review_model END WHERE id=?',
               (chosen.get('key'),chosen.get('key'),view['id']))
    if view['phase']=='implement':
        view['agent_id']=None
        return programmer_quota_handoff(db,view,{'lastError':message})
    from .reviewer_routes import note_session_quota
    view['agent_id']=None
    return note_session_quota(db,view,message)


def launch_rejected(db,task,options,message):
    """Only explicit pre-execution rejection AND native absence permit clearing a receipt."""
    import re
    from . import core
    from .policy_integration import release_task
    if not re.search(r'(?i)(unknown provider|unsupported provider|invalid model|model not found|effort_forbidden|astra_forbidden|não confere com o ticket|sem política validada|no such file or directory|permission denied|invalid configuration|ENOENT)',message):return False
    agent=options.get('agentId')
    if not agent:return False
    try:snapshot=core.native_snapshot(agent)
    except Exception:return False
    view=dict(task);view['agent_id']=agent
    if snapshot is None:
        release_task(db,view,{'kind':'cancelled','native_absent':True,'confirmed':True})
    elif isinstance(snapshot,dict) and not core._snapshot_busy(snapshot) and (snapshot.get('archivedAt') or (snapshot.get('status') or snapshot.get('lifecycle')) in {'error','failed'}):
        if not retire(db,view):return False
    else:return False
    db.execute("UPDATE tasks SET state='blocked',agent_id=NULL,launch_request=NULL,retry_at=NULL,error=?,updated=? WHERE id=?",('Criação rejeitada antes da execução: '+message[-4000:],core.now(),task['id']))
    db.execute('UPDATE jobs SET notified=0 WHERE id=?',(task['job_id'],))
    core.event(db,'launch_rejected',{'agent_id':agent,'error':message[-1200:],'worktree_preserved':True},task['job_id'],task['id']);db.commit()
    return True
