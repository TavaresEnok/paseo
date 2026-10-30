#!/usr/bin/env python3
"""Expose operator-configured ACP metadata; never start Grok or accept inference."""
import json,sys,uuid
from pathlib import Path

def main():
    config=json.loads(Path('/home/enok/srv_projetos/config.json').read_text())
    declared=config.get('agents',{}).get('providers',{}).get('grok',{}).get('models',[])
    models=[{'modelId':m['id'],'name':m.get('label',m['id'])} for m in declared]
    for line in sys.stdin:
        try:request=json.loads(line)
        except ValueError:continue
        if 'id' not in request:continue
        method=request.get('method');result=None;error=None
        if method=='initialize':
            result={'protocolVersion':1,'agentCapabilities':{'loadSession':False},'authMethods':[],
                    'agentInfo':{'name':'grok-configured-metadata','version':'1.0.0'}}
        elif method=='session/new':
            result={'sessionId':'metadata-'+uuid.uuid4().hex,'models':{'currentModelId':'grok-4.7','availableModels':models},
                    'modes':{'currentModeId':'bypassPermissions','availableModes':[{'id':'bypassPermissions','name':'Autônomo'}]}}
        else:error={'code':-32601,'message':'Metadata only. Inference requires controller admission.'}
        response={'jsonrpc':'2.0','id':request['id']}
        response['error' if error else 'result']=error if error else result
        print(json.dumps(response),flush=True)
        if method=='session/new' and not error:
            print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':result['sessionId'],'update':{'sessionUpdate':'available_commands_update','availableCommands':[]}}}),flush=True)
if __name__=='__main__':main()
