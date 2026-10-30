import { z } from 'zod';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const run = promisify(execFile);
export default function(server:any) {
 const sources = [
  ['codex-programmer','Codex novo — Terra programador','Conta exclusiva de programação'],
  ['grok-panel','Grok 4.7 — programador','Assinatura SuperGrok'],
  ['claude-panel','Claude — revisor / gerente reserva','Assinatura Claude'],
  ['antigravity2','Gemini 3.8 Flash Alto — conta 3','Google — conta 3'],
 ];
 for (const [id,label,account] of sources) server.registerUsageSource({
  id,label,input:z.object({}),
  discover:async(scope:any)=>scope.kind==='global'||scope.provider===id||id==='claude-panel'&&scope.provider==='claude'?[{key:`nexoisp-${id}-subscription`,label:account,input:{}}]:[],
  fetch:async()=>{
   try {
    const {stdout}=await run('/home/enok/.local/bin/python3.12',['-m','orchestrator.usage_dashboard',id==='grok-panel'?'grok':id],{cwd:'/home/enok/.local/share/paseo-orchestrator',timeout:25000,maxBuffer:128*1024});
    return JSON.parse(stdout);
   } catch { return {status:'unavailable',windows:[],balances:[],details:[{id:'error',label:'Cota indisponível',value:'Consulta não concluída; tente atualizar.'}]}; }
  }
 });
 return ()=>{};
}
