"""Durable reviewer substitution. Quota is read from catalog evidence or explicit limit errors.

No model is consulted to poll for quota. A clock timestamp alone never restores a role.
"""
from . import core
from .model_limits import load_limits

REAL_REVIEW_FAILURES = ('Revisão reprovou', 'Regressão após revisão', 'Testes falharam')


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS reviewer_routes (
        scope TEXT PRIMARY KEY, state TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
        active_model TEXT, blocked_at REAL, fallback_blocked_at REAL,
        next_check REAL NOT NULL DEFAULT 0, reason TEXT, updated REAL NOT NULL)''')
    db.commit()


def current_route(db):
    initialize(db)
    row = db.execute("SELECT * FROM reviewer_routes WHERE scope='review'").fetchone()
    return dict(row) if row else None


def review_busy(db):
    row = db.execute(
        "SELECT 1 FROM tasks WHERE phase='review' AND state IN ('running','launching','waiting_permission') LIMIT 1"
    ).fetchone()
    return bool(row)


def _review_settings(review):
    return {
        'quota_max_age_seconds': review.get('quota_max_age_seconds', 300),
        'return_min_remaining_fraction': review.get('return_min_remaining_fraction', 0.01),
    }


def failing_model(task):
    if task.get('review_model'):
        return task['review_model']
    selection = core.decode(task.get('selection') or '{}') or {}
    selected = selection.get('selected') or {}
    return selected.get('key')


def quota_failure_reason(task, snapshot, catalog=None):
    """Return why a review session exhausted quota, or None when it did not.

    Explicit limit text (including 'hit your session limit') and fresh catalog
    exhaustion count. Auth, transport, a real review/test failure and a mere
    missing slot do not.
    """
    review = load_limits().get('review') or {}
    if not review.get('fallback_allowed'):
        return None
    snapshot = snapshot or {}
    message = str(snapshot.get('lastError') or snapshot.get('error') or '')
    if message.startswith(REAL_REVIEW_FAILURES):
        return None
    from .supervision import TRANSPORT_OR_AUTH, SLOT_ONLY, explicit_quota_text, quota, quota_error
    # Slot, request throttling, transport and auth win over any quota words in the same error.
    if TRANSPORT_OR_AUTH.search(message) or SLOT_ONLY.search(message):
        return None
    if explicit_quota_text(message):
        return 'explicit_limit'
    if snapshot.get('id') and quota_error(snapshot):
        return 'explicit_limit'
    model_key = failing_model(dict(task))
    if catalog and model_key:
        state, _observed = quota(catalog, model_key, _review_settings(review))
        if state == 'exhausted':
            return 'catalog'
    return None


def _save_route(db, state, generation, active_model, blocked_at, fallback_blocked_at, reason):
    current = current_route(db)
    now = core.now()
    if current:
        db.execute('''UPDATE reviewer_routes SET state=?,generation=?,active_model=?,blocked_at=?,
                      fallback_blocked_at=?,reason=?,updated=? WHERE scope='review' ''',
                   (state, generation, active_model, blocked_at, fallback_blocked_at, reason, now))
    else:
        db.execute('''INSERT INTO reviewer_routes(scope,state,generation,active_model,blocked_at,
                      fallback_blocked_at,reason,updated,next_check) VALUES('review',?,?,?,?,?,?,?,?)''',
                   (state, generation, active_model, blocked_at, fallback_blocked_at, reason, now, 0))


def note_session_quota(db, task, message, evidence='explicit_limit'):
    """Switch only the reviewer. Keep the worktree, digest, phase and attempt."""
    review = load_limits().get('review') or {}
    if not review.get('fallback_allowed'):
        return False
    from .policy_integration import policy_enabled, record_role_exhaustion
    if policy_enabled():
        task = dict(task)
        provider = record_role_exhaustion(db, task, 'reviewer', message or evidence)
        if not provider:
            return False
        from .worker_lifecycle import retire
        if not retire(db,task):return True
        now = core.now()
        db.execute('''UPDATE tasks SET state='queued', phase='review',
                      previous_agent_id=COALESCE(?, previous_agent_id), agent_id=NULL,
                      launch_request=NULL, error=?, retry_at=NULL, updated=? WHERE id=?''',
                   (task.get('agent_id'), 'reviewer_quota:' + (message or evidence)[:400], now, task['id']))
        core.event(db, 'reviewer_quota_noted', {
            'reason': (message or '')[:1000], 'evidence': evidence, 'provider': provider,
            'from_model': failing_model(task), 'phase': 'review', 'attempt': task.get('attempt'),
            'cwd': task.get('cwd'), 'review_digest': task.get('review_digest'),
        }, task.get('job_id'), task.get('id'))
        db.commit()
        return True
    task = dict(task)
    initialize(db)
    route = current_route(db) or {}
    failed = failing_model(task)
    primary = review.get('model')
    fallback = review.get('fallback_model')
    stored = db.execute('SELECT state,agent_id FROM tasks WHERE id=?', (task['id'],)).fetchone()
    if stored and stored['state'] == 'queued' and not stored['agent_id'] and route.get('state') in {'fallback', 'both_exhausted'}:
        return True
    on_fallback = failed == fallback or (route.get('state') in {'fallback', 'fallback_wait'} and failed not in {None, primary})
    now = core.now()
    generation = int(route.get('generation') or 0)
    if on_fallback:
        generation += 1
        _save_route(db, 'both_exhausted', generation, None, route.get('blocked_at') or now, now,
                    (message or '')[:1000])
        waiting = True
        event_kind = 'reviewer_quota_wait'
        error = 'reviewer_quota_wait:' + (message or evidence)[:400]
        target = None
        thinking = None
    else:
        generation += 1
        _save_route(db, 'fallback', generation, fallback, now, route.get('fallback_blocked_at'),
                    (message or '')[:1000])
        waiting = False
        event_kind = 'reviewer_substituted'
        error = 'reviewer_quota:' + (message or evidence)[:400]
        target = fallback
        thinking = review.get('fallback_thinking_option')
    if task.get('agent_id'):
        core.archive_worker(db, task)
    db.execute('''UPDATE tasks SET state='queued', phase='review',
                  previous_agent_id=COALESCE(?, previous_agent_id), agent_id=NULL,
                  launch_request=NULL, error=?, retry_at=?, updated=? WHERE id=?''',
               (task.get('agent_id'), error, (now + 60) if waiting else None, now, task['id']))
    core.event(db, event_kind, {
        'reason': (message or '')[:1000], 'evidence': evidence, 'from_model': failed or primary,
        'to_model': target, 'to_thinking': thinking, 'generation': generation, 'phase': 'review',
        'attempt': task.get('attempt'), 'cwd': task.get('cwd'), 'review_digest': task.get('review_digest'),
        'programmer_model': task.get('model'),
    }, task.get('job_id'), task.get('id'))
    db.commit()
    return True


def consider_return(db, catalog):
    """Restore Sonnet only from positive quota evidence newer than the block.

    An active reviewer is left on its current turn. This does not prompt a model.
    """
    review = load_limits().get('review') or {}
    if not review.get('fallback_allowed') or review.get('auto_return', True) is not True:
        return
    initialize(db)
    route = current_route(db)
    if not route or route['state'] not in {'fallback', 'fallback_wait', 'both_exhausted'}:
        return
    if review_busy(db):
        return
    from .supervision import quota
    settings = _review_settings(review)
    state, observed = quota(catalog or {}, review.get('model'), settings)
    if state == 'available' and observed and observed > (route.get('blocked_at') or 0):
        _save_route(db, 'primary', route['generation'], review.get('model'), route.get('blocked_at'),
                    route.get('fallback_blocked_at'), 'newer_positive_quota')
        core.event(db, 'reviewer_returned', {
            'model': review.get('model'), 'thinking': review.get('thinking_option'),
            'evidence_at': observed, 'blocked_at': route.get('blocked_at'),
            'reason': 'newer_positive_quota',
        })
        db.commit()
        return
    if route['state'] == 'both_exhausted' and review.get('fallback_model'):
        state, observed = quota(catalog or {}, review.get('fallback_model'), settings)
        if state == 'available' and observed and observed > (route.get('fallback_blocked_at') or 0):
            _save_route(db, 'fallback', route['generation'], review.get('fallback_model'),
                        route.get('blocked_at'), route.get('fallback_blocked_at'), 'fallback_quota_restored')
            core.event(db, 'reviewer_fallback_resumed', {
                'model': review.get('fallback_model'), 'thinking': review.get('fallback_thinking_option'),
                'evidence_at': observed, 'blocked_at': route.get('fallback_blocked_at'),
                'reason': 'fallback_quota_restored',
            })
            db.commit()
