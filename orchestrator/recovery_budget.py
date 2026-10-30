"""Per-task automatic recovery budget. Quota/network waits do not spend attempts."""
import hashlib,json,re


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS recovery_budgets(task_id TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, active_seconds REAL NOT NULL DEFAULT 0, same_failure INTEGER NOT NULL DEFAULT 0, signature TEXT, blocked_reason TEXT, extra_attempts INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS recovery_charges(task_id TEXT, identity TEXT, PRIMARY KEY(task_id,identity))')


def charge(db, task, error, settings, *, active_seconds=0, progress_digest=''):
    if not settings.get('enabled'):return None
    from .supervision import TRANSPORT_OR_AUTH,SLOT_ONLY
    from .policy_runtime import explicit_quota_text
    if explicit_quota_text(error) or TRANSPORT_OR_AUTH.search(str(error)) or SLOT_ONLY.search(str(error)):return None
    initialize(db);tid=task['id']
    db.execute('INSERT OR IGNORE INTO recovery_budgets(task_id) VALUES(?)',(tid,))
    row=dict(db.execute('SELECT * FROM recovery_budgets WHERE task_id=?',(tid,)).fetchone())
    if row['blocked_reason']:return row['blocked_reason']
    # A real implementation/review failure only. The caller excludes quota,
    # transport reconciliation and unconfirmed worker retirement.
    text=re.sub(r'\b[0-9a-f]{8,}\b|\b\d+(?:\.\d+)?\b','?',str(error).lower())
    signature=hashlib.sha256((text+'\n'+progress_digest).encode()).hexdigest()
    identity=str(task.get('agent_id') or '')+':'+str(task.get('attempt'))+':'+str(task.get('phase'))
    if db.execute('SELECT 1 FROM recovery_charges WHERE task_id=? AND identity=?',(tid,identity)).fetchone():return None
    db.execute('INSERT INTO recovery_charges VALUES(?,?)',(tid,identity))
    failures=row['failures']+1;seconds=row['active_seconds']+max(0,active_seconds)
    repeated=row['same_failure']+1 if signature==row['signature'] else 1
    reason=None
    if repeated>=settings.get('max_same_failure',3):reason='same_failure_without_progress'
    elif failures>=settings.get('max_automatic_attempts',8)+row['extra_attempts']:reason='automatic_attempt_budget'
    elif seconds>=settings.get('max_active_seconds',14400):reason='active_time_budget'
    db.execute('UPDATE recovery_budgets SET failures=?,active_seconds=?,same_failure=?,signature=?,blocked_reason=? WHERE task_id=?',(failures,seconds,repeated,signature,reason,tid))
    return reason


def assert_recoverable(db,task_id):
    initialize(db)
    row=db.execute('SELECT blocked_reason FROM recovery_budgets WHERE task_id=?',(task_id,)).fetchone()
    if row and row[0]:raise ValueError('Orçamento de recuperação atingido: '+row[0]+'. É necessária extensão explícita do operador; não repetir o mesmo recover.')


def extend(db,task_id,attempts,reason,*,caller_agent_id=None):
    if caller_agent_id:raise ValueError('Extensão de orçamento reservada ao operador humano.')
    if type(attempts) is not int or not 1<=attempts<=10 or not str(reason).strip():raise ValueError('Informe 1..10 tentativas e motivo.')
    initialize(db)
    if not db.execute('SELECT 1 FROM recovery_budgets WHERE task_id=?',(task_id,)).fetchone():raise ValueError('Orçamento inexistente.')
    previous=dict(db.execute('SELECT * FROM recovery_budgets WHERE task_id=?',(task_id,)).fetchone())
    db.execute('UPDATE recovery_budgets SET extra_attempts=extra_attempts+?,same_failure=0,active_seconds=0,blocked_reason=NULL WHERE task_id=?',(attempts,task_id))
    # Audit retained in the controller event stream, never erase prior charges.
    from . import core
    core.event(db,'recovery_budget_operator_extension',{'attempts':attempts,'reason':reason,'previous':previous},task_id=task_id)
    db.commit()
