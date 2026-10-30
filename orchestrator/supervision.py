"""Durable quota-based manager transfer. No model calls for quota polling."""
import datetime
import json
from pathlib import Path
import re
import uuid
import threading
_prefetched=threading.local()

from . import core, supervisor
from .model_limits import load_limits
from .resources import assess_resources

BUSY = {'running', 'starting', 'loading', 'initializing', 'waiting_permission', 'awaiting_permission'}


def timestamp(value):
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (AttributeError, ValueError, TypeError):
        return None


def quota(catalog, model_key, settings):
    entry = next((m for m in catalog.get('models', [])
                  if m['provider']+'/'+m['id'] == model_key), {})
    evidence = entry.get('quota', {})
    observed = timestamp(evidence.get('observed_at'))
    fresh = observed is not None and 0 <= core.now()-observed <= settings.get('quota_max_age_seconds', 300)
    windows = evidence.get('windows', [])
    fractions = [w.get('remaining_fraction') for w in windows]
    known = bool(fractions) and all(isinstance(n, (int, float)) and not isinstance(n, bool) and 0 <= n <= 1 for n in fractions)
    state = 'unknown'
    if fresh and evidence.get('source'):
        if any(w.get('status') == 'exhausted' or w.get('remaining_fraction') == 0 for w in windows):
            state = 'exhausted'
        elif (known and min(fractions) >= settings.get('return_min_remaining_fraction', .01)
              and entry.get('authenticated') is True and entry.get('available') is True
              and entry.get('cost', {}).get('verified') is True
              and entry.get('cost', {}).get('additional_cost') == 0):
            state = 'available'
    return state, observed


def busy(agent):
    return bool(agent.get('activeTurn') or agent.get('pendingPermissions') or agent.get('status') in BUSY)


def thinking_of(agent):
    runtime = agent.get('runtimeInfo') or {}
    labels = agent.get('labels') or {}
    return (agent.get('thinkingOptionId') or agent.get('effectiveThinkingOptionId')
            or runtime.get('thinkingOptionId') or runtime.get('effectiveThinkingOptionId')
            or labels.get('flow.supervisor.thinking'))


def work_agent(agent):
    """Reviewers and programmers, including legacy ones, are not managers."""
    labels = agent.get('labels') or {}
    if labels.get('flow.phase') in {'review', 'implement'}:
        return True
    if labels.get('flow.task'):
        return True
    return labels.get('flow.role') in {'worker', 'reviewer', 'programmer'}


def recorded_fallback(db, agent):
    labels = agent.get('labels') or {}
    if labels.get('flow.supervisor.role') == 'fallback':
        return True
    if str(labels.get('flow.supervisor.request') or '').endswith('-fallback'):
        return True
    return bool(db.execute('SELECT 1 FROM supervisor_routes WHERE fallback_id=?', (agent.get('id'),)).fetchone())


def _same_effort_as_reviewer(key, settings, review):
    effort = settings.get('primary_thinking')
    if not effort:
        return True
    if key == review.get('model') and review.get('thinking_option') == effort:
        return True
    fallback_effort = review.get('fallback_thinking_option') or review.get('thinking_option')
    return key == review.get('fallback_model') and fallback_effort == effort


def _in_manager_area(path):
    """Management trees only. Worker worktrees are not manager cwd."""
    resolved = Path(path).resolve()
    worktrees = core.WORKTREES.resolve()
    if resolved == worktrees or worktrees in resolved.parents:
        return False
    root = getattr(core, 'MANAGER_ROOT', None)
    if root is not None:
        root = Path(root).resolve()
        if resolved == root or root in resolved.parents:
            return True
    dev = core.DEV.resolve()
    return resolved == dev or dev in resolved.parents


def discoverable_manager(agent, settings, limits, db):
    """Primary manager: current model, supervisor role and effort, valid cwd.

    Sol reviewers share the manager model id under the new policy. Medium/low
    effort, work phases and previous-policy substitutes are not registered.
    """
    if not isinstance(agent, dict) or agent.get('archivedAt') or work_agent(agent):
        return False
    key = agent.get('provider', '') + '/' + str(agent.get('model'))
    if key != settings.get('primary_model'):
        from .policy_integration import policy_enabled, verify_ticket, _token
        if not policy_enabled(limits) or recorded_fallback(db, agent):
            return False
        try:
            row = db.execute("SELECT ticket_json FROM admission_tickets WHERE agent_id=? AND role='manager'", (agent['id'],)).fetchone()
            ticket = json.loads(row['ticket_json']) if row else {}
            if not (verify_ticket(ticket, _token()) and ticket.get('agent_id') == agent['id']
                    and key == ticket.get('provider', '') + '/' + ticket.get('model', '')
                    and thinking_of(agent) == ticket.get('effort')):
                return False
            core.manager_cwd(agent.get('cwd'))
            return True
        except (ValueError, TypeError, OSError):
            return False
    try:
        cwd = core.manager_cwd(agent.get('cwd'))
    except (ValueError, TypeError):
        return False
    if recorded_fallback(db, agent):
        return False
    labels = agent.get('labels') or {}
    thinking = thinking_of(agent)
    review = (limits or {}).get('review') or {}
    shared = key in {review.get('model'), review.get('fallback_model')}
    if labels.get('flow.supervisor.role') == 'fallback':
        return False
    if not shared:
        # A distinct manager model can still be discovered without UI labels.
        if labels.get('flow.role') not in {None, 'supervisor'}:
            return False
        if thinking not in {None, settings.get('primary_thinking')}:
            return False
        return True
    # The same model id is also a reviewer. Exact manager effort separates them.
    # Medium/low reviewers and work agents never match. If a future policy gives
    # both roles the same effort, an explicit supervisor label is required.
    if labels.get('flow.role') not in {None, 'supervisor'}:
        return False
    if thinking != settings.get('primary_thinking') and not ((settings.get('adaptive_effort') or {}).get('enabled') and key == 'codex/gpt-6.1-sol' and thinking in {'medium','high'} and labels.get('flow.role') == 'supervisor'):
        return False
    if labels.get('flow.role') == 'supervisor':
        return True
    if _same_effort_as_reviewer(key, settings, review) or not _in_manager_area(cwd):
        return False
    return True


def migrate_supervisor_route(db, old_primary_id, new_primary_id, agent):
    """Operator migration to a manager that already matches the active policy.

    Does not call a provider, does not infer a replacement from the clock, and
    does not resume paused or canceled plans.
    """
    initialize(db)
    limits = load_limits()
    settings = limits.get('supervision') or {}
    if not isinstance(agent, dict) or agent.get('id') != new_primary_id:
        raise RuntimeError('Identidade do gerente não confere')
    if not discoverable_manager(agent, settings, limits, db):
        raise RuntimeError('Novo gerente não corresponde à política vigente')
    if old_primary_id == new_primary_id:
        return {'primary_id': new_primary_id, 'migrated': False}
    row = db.execute('SELECT active_id,fallback_id,state FROM supervisor_routes WHERE primary_id=?',
                     (old_primary_id,)).fetchone()
    sources = [old_primary_id]
    if row:
        if row['active_id'] and row['active_id'] not in sources:
            sources.append(row['active_id'])
        if row['fallback_id'] and row['fallback_id'] not in sources:
            sources.append(row['fallback_id'])
    placeholders = ','.join('?' for _ in sources)
    db.execute(f"UPDATE jobs SET supervisor_id=?,updated=? WHERE supervisor_id IN ({placeholders}) AND state NOT IN ('paused','canceled')",
               (new_primary_id, core.now(), *sources))
    if row and row['state'] != 'superseded':
        db.execute("UPDATE supervisor_routes SET state='superseded',updated=? WHERE primary_id=?",
                   (core.now(), old_primary_id))
    db.execute("INSERT OR IGNORE INTO supervisor_routes(primary_id,active_id,state,updated) VALUES(?,?,'primary',?)",
               (new_primary_id, new_primary_id, core.now()))
    core.event(db, 'supervisor_route_migrated', {
        'previous': old_primary_id, 'replacement': new_primary_id,
        'model': settings.get('primary_model'), 'thinking': settings.get('primary_thinking'),
        'reason': 'explicit_operator_migration',
    })
    db.commit()
    return {'primary_id': new_primary_id, 'migrated': True}


TRANSPORT_OR_AUTH = re.compile(
    r'auth|unauthor|forbidden|transport|connection|timed out|timeout|econn|network|\btls\b|\bssl\b|proxy',
    re.I)
SLOT_ONLY = re.compile(r'\bslot\b|concurrency|too many requests|at capacity', re.I)
# Franchise exhaustion only. Generic request throttling (rate_limit) is not quota.
QUOTA_TEXT = re.compile(
    r'quota[ _-]?(?:exceeded|exhausted|reached)|(?:usage|token|session)[ _-]?limit|hit your (?:session )?limit|out of (?:tokens|usage)',
    re.I)


def explicit_quota_text(message):
    """True for an unambiguous quota limit, including 'hit your session limit'.

    Auth, transport, timeouts and request-slot throttling never qualify, even
    when the same sentence also mentions a usage or session limit.
    """
    text = str(message or '')
    if not text or TRANSPORT_OR_AUTH.search(text) or SLOT_ONLY.search(text):
        return False
    return bool(QUOTA_TEXT.search(text))


def quota_event(agent, since=0):
    """Return the native error identity, never the time of a controller poll."""
    events = []
    message = str(agent.get('lastError') or agent.get('error') or '')
    at = timestamp(agent.get('updatedAt'))
    if explicit_quota_text(message) and (at is None or at > since):
        events.append((message, at))
    if agent.get('attentionReason') == 'error' and agent.get('id'):
        timeline = getattr(_prefetched,'timelines',{}).get(agent['id'],{'entries':[]})
        for row in timeline.get('entries', []):
            item = row.get('item', {})
            at = timestamp(row.get('timestamp'))
            message = str(item.get('message', ''))
            if (item.get('type') in {'error', 'notification'} and at is not None
                    and at > since and explicit_quota_text(message)):
                events.append((message, at))
    return max(events, key=lambda event: event[1] or 0) if events else None


def quota_error(agent, since=0):
    """An ordinary auth/transport/tool failure is not proof of exhausted quota."""
    return quota_event(agent, since) is not None


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS supervisor_routes (
        primary_id TEXT PRIMARY KEY, active_id TEXT NOT NULL, state TEXT NOT NULL,
        generation INTEGER NOT NULL DEFAULT 0, fallback_id TEXT, blocked_at REAL,
        next_check REAL NOT NULL DEFAULT 0, pending TEXT, updated REAL NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS deferred_manager_archives (
        agent_id TEXT PRIMARY KEY, deferred_at REAL NOT NULL, children_json TEXT NOT NULL DEFAULT '[]')''')
    db.commit()


def manager_descendants(agents, parent):
    descendants = {parent}
    changed = True
    while changed:
        changed = False
        for child in agents.values():
            labels = child.get('labels') or {}
            links = {labels.get('parent-agent-id'), child.get('parentAgentId')}
            if links & descendants and child['id'] not in descendants:
                descendants.add(child['id'])
                changed = True
    return descendants - {parent}


def cleanup_deferred_manager_archives(db, agents):
    """Use this reconciliation's complete metadata; never poll or expire a parent."""
    if agents is None:
        return
    # Remember children even while work blocks cleanup; later absence from a
    # snapshot is not positive terminal proof for a previously observed child.
    for row in db.execute('SELECT agent_id,children_json FROM deferred_manager_archives').fetchall():
        children = set(core.decode(row['children_json'])) | manager_descendants(agents, row['agent_id'])
        db.execute('UPDATE deferred_manager_archives SET children_json=? WHERE agent_id=?',
                   (core.encoded(sorted(children)), row['agent_id']))
    db.commit()
    # Mapping can be incomplete for a create with an unknown receipt. Keep a
    # conservative host-wide barrier, including paused work with pending create.
    if db.execute("SELECT 1 FROM tasks WHERE state IN ('running','launching','waiting_permission','integrating') OR launch_request IS NOT NULL LIMIT 1").fetchone():
        return
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'capacity_leases' in tables and db.execute(
            "SELECT 1 FROM capacity_leases WHERE status!='released' OR uncertain!=0 LIMIT 1").fetchone():
        return
    owners = {r[0] for r in db.execute('SELECT active_id FROM supervisor_routes')}
    if 'manager_owners' in tables:
        owners.update(r[0] for r in db.execute('SELECT agent_id FROM manager_owners'))
    for route in db.execute('SELECT primary_id,state,pending FROM supervisor_routes'):
        if route['state'].startswith('switching_'):
            owners.add(route['primary_id'])
            pending = core.decode(route['pending']) or {}
            owners.add((pending.get('options') or {}).get('agentId'))
    terminal = {'completed', 'done', 'failed', 'canceled', 'cancelled', 'stopped', 'terminated', 'archived'}
    for row in db.execute('SELECT agent_id,children_json FROM deferred_manager_archives').fetchall():
        parent = row['agent_id']
        agent = agents.get(parent)
        if parent in owners or not agent or busy(agent):
            continue
        # Walk descendants too: an archived direct child can still have a live
        # descendant in a partial lifecycle snapshot. Idle is not terminal proof.
        descendants = set(core.decode(row['children_json'])) | manager_descendants(agents, parent)
        db.execute('UPDATE deferred_manager_archives SET children_json=? WHERE agent_id=?',
                   (core.encoded(sorted(descendants)), parent))
        db.commit()
        if any(aid not in agents or busy(agents[aid]) or not (agents[aid].get('archivedAt') or
               agents[aid].get('status') in terminal) for aid in descendants):
            continue
        if not agent.get('archivedAt'):
            try:
                result = core.bridge('archive', agentId=parent)
            except Exception:
                continue
            if not isinstance(result, dict) or not result.get('archivedAt'):
                continue  # Unknown receipt is retained; no clock-based cleanup.
        db.execute('DELETE FROM deferred_manager_archives WHERE agent_id=?', (parent,))
        db.commit()


def handoff(db, route, source_id, destination):
    jobs = [dict(j) for j in db.execute(
        "SELECT id,objective,state,repo,branch FROM jobs WHERE supervisor_id IN (?,?) AND state NOT IN ('paused','canceled')",
        (route['primary_id'], route['active_id']))]
    for job in jobs:
        job['tasks'] = [dict(t) for t in db.execute(
            'SELECT task_key,state,phase,error,commit_sha FROM tasks WHERE job_id=?', (job['id'],))]
        for task in job['tasks']:
            if task.get('error'):task['error']=task['error'][:500]
    timeline = getattr(_prefetched,'timelines',{}).get(source_id)
    if timeline is None:raise RuntimeError('Histórico ainda indisponível; transferência aguardará próxima consulta sem perder contexto.')
    messages = []
    for row in timeline.get('entries', []):
        item = row.get('item', {})
        if item.get('type') in {'user_message', 'assistant_message'}:
            text = str(item.get('text', ''))
            # Do not recursively quote previous machine handoffs.
            if not text.startswith('[Transferência automática de gerência]'):
                messages.append({'role': item['type'], 'text': text[:4000]})
    snapshot = getattr(_prefetched,'agents',{}).get(source_id)
    if not snapshot:raise RuntimeError('Snapshot do gerente indisponível.')
    cwd = core.manager_cwd(snapshot['cwd'])
    context = ''
    path = cwd/'.paseo-context.md'
    if path.is_file() and not path.is_symlink():
        context = path.read_text()[:8000]
    payload = {'destination': destination, 'jobs': jobs, 'recent_messages': messages[-12:], 'context': context}
    if len(core.encoded(payload)) > 48000:
        # Preserve valid structured context and the newest user requests. The
        # complete plan and task history remain available through paseo-flow.
        payload['recent_messages']=[{**m,'text':m['text'][:2000]} for m in messages[-6:]]
        for job in payload['jobs']:
            counts={}
            for task in job['tasks']:counts[task['state']]=counts.get(task['state'],0)+1
            job['task_counts']=counts
            job['tasks']=[t for t in job['tasks'] if t['state']!='done'][:10]
    from .model_limits import role_summary
    return ('[Transferência automática de gerência]\n'
            + role_summary(load_limits()) + '\n'
            'Preserve o plano, as decisões, arquivos e tarefas já concluídas. Nunca reenvie nem duplique um plano existente. '
            'Planos pausados permanecem assim até pedido explícito do usuário para continuar; esse pedido autoriza paseo-flow resume sem nova confirmação. Planos cancelados permanecem cancelados. Se há tarefas executando, registre o contexto, confirme brevemente e aguarde os eventos. '
            'Somente se ainda não existe plano, retome a última solicitação real do usuário.\n'
            + core.encoded(payload))


def bind_jobs(db, primary, previous, destination):
    # Paused/canceled plans are never resumed or reassigned by this mechanism.
    db.execute("UPDATE jobs SET supervisor_id=?,updated=? WHERE supervisor_id IN (?,?) AND state NOT IN ('paused','canceled')",
               (destination, core.now(), primary, previous))
    from .policy_integration import policy_enabled, single_manager
    if not policy_enabled():
        return
    from .policy_integration import _chat_expr
    rows = db.execute(f"""SELECT DISTINCT {_chat_expr(db)} AS chat_id FROM jobs
        LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id
        WHERE jobs.supervisor_id=? AND jobs.state NOT IN ('paused','canceled','cancelled')""", (destination,)).fetchall()
    for row in rows:
        if row['chat_id']:
            single_manager(db, row['chat_id'], destination)


def transition(db, route, primary, settings, agents=None):
    pending = core.decode(route['pending'])
    try:
        if route['state'] == 'switching_to_fallback':
            # createAgent has a durable native receipt. A timeout repeats the
            # exact request key instead of spawning a second replacement.
            result = supervisor.start(pending['cwd'], pending['prompt'], fallback=True,
                                      workspace_id=pending.get('workspace_id'),
                                      idempotency_key=pending['request_key'], native_options=pending['options'],
                                      action=pending.get('action'))
            replacement = result['agent_id']
            bind_jobs(db, route['primary_id'], route['active_id'], replacement)
            db.execute("UPDATE supervisor_routes SET active_id=?,fallback_id=?,state='fallback',pending=NULL,next_check=?,updated=? WHERE primary_id=?",
                       (replacement, replacement, core.now()+30, core.now(), route['primary_id']))
            opts = pending.get('options') or {}
            actual_model = f"{opts['provider']}/{opts['model']}" if opts.get('provider') and opts.get('model') else settings['fallback_model']
            actual_effort = opts.get('thinkingOptionId') or settings['fallback_thinking']
            core.event(db, 'supervisor_failover', {'previous': route['primary_id'], 'replacement': replacement,
                        'model': actual_model, 'thinking': actual_effort, 'generation': route['generation']})
        else:
            # messageId is native send de-duplication; persist it BEFORE send.
            core.bridge('send', agentId=route['primary_id'], prompt=pending['prompt'],
                        options={'messageId': pending['message_id'], 'activeTurnBehavior': 'steer'})
            previous = route['active_id']
            bind_jobs(db, route['primary_id'], previous, route['primary_id'])
            db.execute("UPDATE supervisor_routes SET active_id=primary_id,state='primary',pending=NULL,next_check=?,updated=? WHERE primary_id=?",
                       (core.now()+30, core.now(), route['primary_id']))
            core.event(db, 'supervisor_failback', {'previous': previous, 'replacement': route['primary_id'],
                        'model': settings['primary_model'], 'thinking': settings['primary_thinking'], 'generation': route['generation']})
            if previous != route['primary_id']:
                # SDK archive cascades to workers. Retain the public idle caller
                # for healthy children and exact pending-create receipt replay.
                db.execute('INSERT OR IGNORE INTO deferred_manager_archives VALUES(?,?,?)',
                           (previous, core.now(), core.encoded(sorted(manager_descendants(agents or {}, previous)))))
                core.event(db, 'supervisor_archive_deferred', {'agent_id': previous})
            db.commit()
    except Exception as error:
        # Keep the current owner and the exact pending request on uncertainty.
        db.execute('UPDATE supervisor_routes SET next_check=?,updated=? WHERE primary_id=?',
                   (core.now()+settings.get('retry_seconds', 60), core.now(), route['primary_id']))
        core.event(db, 'supervisor_transfer_pending', {'primary_id': route['primary_id'],
                    'direction': route['state'], 'error': str(error)[:1000]})
    db.commit()


def reconcile():
    from .operator_hold import active
    if active():return
    entries=core.bridge('agents',timeout=20,options={'includeBackground':True}).get('entries')
    if not isinstance(entries,list):return
    agents={e.get('agent',e)['id']:e.get('agent',e) for e in entries}
    timelines={}
    for agent in agents.values():
        if work_agent(agent):continue
        if agent.get('id') and not busy(agent):
            try:timelines[agent['id']]=core.bridge('timeline',timeout=15,agentId=agent['id'],options={'limit':40})
            except Exception:continue
    _prefetched.agents=agents;_prefetched.timelines=timelines
    from .supervision_io import CONTEXT
    CONTEXT.enabled=True
    try:return _reconcile(entries)
    finally:
        CONTEXT.enabled=False
        _prefetched.agents={};_prefetched.timelines={}

@core.serialized
def _reconcile(entries):
    from .operator_hold import active
    if active():return
    settings = load_limits().get('supervision', {})
    if not settings.get('enabled'):
        return
    catalog = json.loads((core.STATE/'catalog.json').read_text())
    availability, quota_at = quota(catalog, settings['primary_model'], settings)
    # Snapshot collected before taking the mutation lock.
    if not isinstance(entries, list):
        return  # An unavailable snapshot cannot prove children terminal.
    agents = {e.get('agent', e)['id']: e.get('agent', e) for e in entries}
    with core.database() as db:
        initialize(db)
        cleanup_deferred_manager_archives(db, agents)
        for agent in agents.values():
            if not discoverable_manager(agent, settings, load_limits(), db):
                continue
            # Unlabeled managers stay when effort and cwd separate them from reviewers.
            db.execute("INSERT OR IGNORE INTO supervisor_routes(primary_id,active_id,state,updated) VALUES(?,?,'primary',?)",
                       (agent['id'], agent['id'], core.now()))
        db.commit()
        for row in db.execute('SELECT * FROM supervisor_routes').fetchall():
            route = dict(row)
            if route['state'] == 'superseded' or route['next_check'] > core.now():
                continue
            from .policy_integration import policy_enabled, reconcile_manager_route
            if policy_enabled():
                reconcile_manager_route(db, route, agents, settings)
                continue
            primary = agents.get(route['primary_id'])
            if not primary or primary.get('archivedAt'):
                continue
            # Previous-policy routes stay dormant until an explicit migration.
            key = primary.get('provider', '')+'/'+str(primary.get('model'))
            if key != settings.get('primary_model'):
                continue
            thinking = thinking_of(primary)
            if thinking and thinking != settings.get('primary_thinking'):
                continue
            owners = (route['primary_id'], route['active_id'])
            linked = db.execute('SELECT state FROM jobs WHERE supervisor_id IN (?,?)', owners).fetchall()
            if linked and all(j['state'] in {'paused', 'canceled'} for j in linked):
                continue
            # An active manager finishes its turn before surrendering ownership.
            current = agents.get(route['active_id'])
            if not current or busy(current):
                continue
            if route['state'].startswith('switching_'):
                transition(db, route, primary, settings, agents)
                continue
            if route['state'] == 'primary':
                if availability != 'exhausted' and not quota_error(primary, route['blocked_at'] or 0):
                    continue
                db.execute("UPDATE supervisor_routes SET state='fallback_wait',generation=generation+1,blocked_at=?,updated=? WHERE primary_id=?",
                           (core.now(), core.now(), route['primary_id']))
                db.commit()
                route = dict(db.execute('SELECT * FROM supervisor_routes WHERE primary_id=?', (route['primary_id'],)).fetchone())
            if (route['state'] in {'fallback', 'fallback_wait'} and settings.get('auto_return')
                    and availability == 'available' and quota_at > (route['blocked_at'] or 0)):
                if busy(primary) or not assess_resources()['allowed']:
                    continue
                pending = {'prompt': handoff(db, route, route['active_id'], settings['primary_model']),
                           'message_id': str(uuid.uuid5(uuid.NAMESPACE_URL, f"supervisor-return-{route['primary_id']}-{route['generation']}"))}
                db.execute("UPDATE supervisor_routes SET state='switching_to_primary',pending=?,updated=? WHERE primary_id=?",
                           (core.encoded(pending), core.now(), route['primary_id']))
            elif route['state'] == 'fallback_wait':
                if not assess_resources()['allowed']:
                    continue
                pending = {'cwd': primary['cwd'], 'workspace_id': primary.get('workspaceId'),
                           'prompt': handoff(db, route, route['primary_id'], settings['fallback_model']),
                           'request_key': f"supervisor-route-{route['primary_id']}-{route['generation']}-fallback"}
                try:
                    pending['options'] = supervisor.prepare(pending['cwd'], pending['prompt'], fallback=True,
                                                            workspace_id=pending.get('workspace_id'),
                                                            idempotency_key=pending['request_key'])
                except RuntimeError:
                    db.execute('UPDATE supervisor_routes SET next_check=? WHERE primary_id=?',
                               (core.now()+settings.get('retry_seconds', 60), route['primary_id']))
                    db.commit()
                    continue
                db.execute("UPDATE supervisor_routes SET state='switching_to_fallback',pending=?,updated=? WHERE primary_id=?",
                           (core.encoded(pending), core.now(), route['primary_id']))
            else:
                continue
            db.commit()
            route = dict(db.execute('SELECT * FROM supervisor_routes WHERE primary_id=?', (route['primary_id'],)).fetchone())
            transition(db, route, primary, settings, agents)
