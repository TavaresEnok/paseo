"""Durable chat-scoped notification batching with immediate blockers."""
import json
import uuid


def deliver(db, jobs, core, window=20):
    db.execute('CREATE TABLE IF NOT EXISTS notification_wait(job_id TEXT PRIMARY KEY, first_seen REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS notification_outbox(chat_id TEXT PRIMARY KEY, message_id TEXT NOT NULL, payload TEXT NOT NULL)')
    groups={}
    for row in jobs:
        job=dict(row)
        if not job.get('supervisor_id'):
            db.execute('UPDATE jobs SET notified=1 WHERE id=?',(job['id'],));continue
        db.execute('INSERT OR IGNORE INTO notification_wait VALUES(?,?)',(job['id'],core.now()))
        groups.setdefault(job['supervisor_id'],[]).append(job)
    db.commit()
    for chat, batch in groups.items():
        if db.execute('SELECT 1 FROM notification_outbox WHERE chat_id=?',(chat,)).fetchone():continue
        first=min(db.execute('SELECT first_seen FROM notification_wait WHERE job_id=?',(j['id'],)).fetchone()[0] for j in batch)
        urgent=any(j['state']!='done' for j in batch)
        if not urgent and core.now()-first<window:continue
        summary=[]
        for job in batch:
            core.report(job['id'])
            summary.append(f"{job['id']}: {job['state']} (paseo-flow report {job['id']})")
        prompt='Evento do controlador: '+ '; '.join(summary)+'.\nConsulte os relatórios compactos. Resolva bloqueios recuperáveis pelo controlador, preservando recibos e entregas; não duplique executores. Após conclusão, prossiga ao próximo lote do backlog já autorizado. Preserve pausas explícitas e escopo. Delegue implementação e exija revisão independente. A política vigente já está nas instruções da sessão; consulte model-limits.json se necessário. Não releia logs completos sem necessidade.'
        payload={'prompt':prompt,'jobs':[{k:j[k] for k in ('id','state','updated')} for j in batch]}
        db.execute('INSERT INTO notification_outbox VALUES(?,?,?)',(chat,str(uuid.uuid4()),json.dumps(payload)))
        db.commit()
    for row in db.execute('SELECT * FROM notification_outbox').fetchall():
        row=dict(row);data=json.loads(row['payload'])
        # A persisted retry must not awaken a plan that was paused in the meantime.
        eligible=[]
        for j in data['jobs']:
            current=db.execute('SELECT state,updated,notified FROM jobs WHERE id=?',(j['id'],)).fetchone()
            if current and current['state']==j['state'] and current['updated']==j['updated'] and not current['notified']:eligible.append(j)
        if len(eligible)!=len(data['jobs']):
            db.execute('DELETE FROM notification_outbox WHERE chat_id=?',(row['chat_id'],));db.commit();continue
        try:
            core.bridge('send',agentId=row['chat_id'],prompt=data['prompt'],options={'messageId':row['message_id'],'activeTurnBehavior':'steer'})
        except Exception as exc:
            core.event(db,'notification_pending',{'error':str(exc)},data['jobs'][0]['id']);db.commit();continue
        for j in data['jobs']:
            db.execute('UPDATE jobs SET notified=1 WHERE id=? AND state=? AND updated=?',(j['id'],j['state'],j['updated']))
            db.execute('DELETE FROM notification_wait WHERE job_id=?',(j['id'],))
        core.event(db,'notification_batch_sent',{'chat_id':row['chat_id'],'jobs':[j['id'] for j in data['jobs']],'message_id':row['message_id']},data['jobs'][0]['id'])
        db.execute('DELETE FROM notification_outbox WHERE chat_id=?',(row['chat_id'],));db.commit()
