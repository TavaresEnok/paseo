"""Offline admission only for accounts owned exclusively by this host.

Shared-account workers and manager changes always wait for the coordinator.
Native admission still verifies the signed ticket and this durable local lease.
"""
import json,uuid

def local_client(db,provider):
    from .model_limits import load_limits
    from .policy_integration import CapacityUnavailable
    limits=load_limits()
    allowed=(limits.get('runtime_policy') or {}).get('offline_admission_providers',[])
    if provider not in allowed:return None
    class Local:
        def register(self,*args,**kwargs):return {'registered':True}
        def status(self):return {'mode':'dedicated_accounts_offline'}
        def acquire(self,chat,task,role,request,metadata):
            if role!='programmer':raise CapacityUnavailable('offline_role_forbidden')
            key=metadata.get('requested_model_key') or ''
            if key.split('/',1)[0]!=provider:raise CapacityUnavailable('offline_provider_mismatch')
            old=db.execute("SELECT lease_id,agent_id FROM capacity_leases WHERE request_id=? AND status IN ('held','uncertain')",(request,)).fetchone()
            if old and not str(old['lease_id']).startswith('local-'):
                return {'granted':False,'reason':'coordinator_required_for_existing_lease'}
            count=db.execute("SELECT count(*) FROM capacity_leases WHERE chat_id=? AND status!='released'",(chat,)).fetchone()[0]
            if not old and count>=int(limits.get('workers_per_chat',10)):
                return {'granted':False,'reason':'chat_worker_cap'}
            return {'granted':True,'lease_id':old['lease_id'] if old else 'local-'+uuid.uuid4().hex,'model_key':key,'thinking_option':metadata.get('requested_thinking_option'),'reason':'dedicated_account_offline'}
        def bind(self,lease,agent):return {'bound':True}
    return Local()
