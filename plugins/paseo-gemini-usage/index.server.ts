import { z } from 'zod';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const run = promisify(execFile);
export default function(server: any) {
 for (const [provider, number, dbName] of [["antigravity2",3,"gemini2"]] as const) server.registerUsageSource({
  id:provider,label:`Gemini 3.8 Flash Alto — conta ${number}`,input:z.object({}),
  discover:async(scope:any)=>scope.kind==='global'||scope.provider===(provider)?[{key:`nexoisp-${provider}-oauth`,label:`Google — conta ${number}`,harness:'Antigravity',input:{}}]:[],
  fetch:async()=>{
   const script=`import json,sqlite3\np='/home/enok/srv_projetos/orchestration/evidence/${dbName}-usage.sqlite3'\ndb=sqlite3.connect('file:'+p+'?mode=ro',uri=True)\nr=db.execute('SELECT coalesce(sum(input),0),coalesce(sum(output),0),coalesce(sum(cached),0),coalesce(sum(thinking),0) FROM usage').fetchone()\nh=db.execute('SELECT status,at FROM health WHERE id=1').fetchone()\nprint(json.dumps(list(r)+list(h or ['unknown',None])))`;
   const {stdout}=await run('/home/enok/.local/bin/python3.12',['-c',script],{timeout:5000});
   const [input,output,cached,thinking,health,observed]=JSON.parse(stdout);
   return {status:'available',planLabel:`Google — conta ${number} · OAuth`,windows:[],balances:[{id:'measured_tokens',label:'Tokens registrados neste servidor',used:input+output,unit:'tokens'}],details:[{id:'quota_state',label:'Última resposta de quota',value:health==='exhausted'?'Esgotada; aguardando recuperação confirmada':health==='available'?'Última execução concluída; saldo desconhecido':'Desconhecida'},{id:'input',label:'Entrada',value:String(input)},{id:'output',label:'Saída',value:String(output)},{id:'cached',label:'Cache',value:String(cached)},{id:'thinking',label:'Raciocínio informado',value:String(thinking)},{id:'scope',label:'Medição',value:'Desde a ativação; não representa saldo da assinatura. Raciocínio já incluso na saída quando reportado pelo CLI.'}]};
  }
 });
 return ()=>{};
}
