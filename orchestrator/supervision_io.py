"""Poll native transition receipts without holding the scheduler mutation lock."""
from concurrent.futures import ThreadPoolExecutor
import threading,json,hashlib
CONTEXT=threading.local()
_POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='paseo-manager-io')
_LOCK=threading.Lock()
_PENDING={}
class Pending(RuntimeError):pass

def call(action,timeout,kwargs):
    from . import core
    identity=hashlib.sha256(json.dumps([action,kwargs],sort_keys=True).encode()).hexdigest()
    def execute():
        from .operator_hold import require_running
        require_running()
        return core._bridge_sync(action,timeout=timeout,**kwargs)
    with _LOCK:
        future=_PENDING.get(identity)
        if future is None:
            future=_POOL.submit(execute);_PENDING[identity]=future
        if not future.done():raise Pending('Operação nativa de gerência em andamento; recibo preservado.')
        del _PENDING[identity]
    return future.result()
