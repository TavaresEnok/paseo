import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const dir=mkdtempSync(join(tmpdir(),'paseo-permission-test-'));
try {
 const paths={
  '/home/enok/srv_projetos/config/profiles.json':join(dir,'profiles.json'),
  '/home/enok/srv_projetos/config/model-limits.json':join(dir,'models.json'),
  '/home/enok/srv_projetos/config/autonomy.json':join(dir,'autonomy.json'),
  '/home/enok/srv_projetos/orchestration/evidence/grok-billing.json':join(dir,'billing.json'),
  '/home/enok/srv_projetos/logs/policy.jsonl':join(dir,'audit.jsonl'),
 };
 writeFileSync(paths['/home/enok/srv_projetos/config/profiles.json'],JSON.stringify({max_concurrent_executors:3}));
 writeFileSync(paths['/home/enok/srv_projetos/config/autonomy.json'],JSON.stringify({unrestricted_tools:true,unattended_development:true}));
 writeFileSync(paths['/home/enok/srv_projetos/config/model-limits.json'],readFileSync('model-limits.fixture.json'));
 writeFileSync(paths['/home/enok/srv_projetos/orchestration/evidence/grok-billing.json'],JSON.stringify({timestamp_utc:new Date().toISOString(),subscription_only_evidence:true,credential_source:'grok_cli',results:{billing:{http_status:200,unified_billing:true,remaining_percent:99,prepaid_cents:0},auto_topup:{http_status:200,enabled:false}}}));
 let source=readFileSync(process.env.POLICY_TEST_SOURCE || 'policy.mjs','utf8');for(const [from,to] of Object.entries(paths))source=source.replaceAll(from,to);
 writeFileSync(join(dir,'policy.mjs'),source);
 const p=await import(pathToFileURL(join(dir,'policy.mjs')));
 for(const cmd of ['ls','ls /tmp','paseo-flow status','paseo-flow recover test --reason example','git push origin main','sudo systemctl status example'])assert.equal(p.classifyCommand(cmd,'/tmp'),'allow');
 for(const tool of ['Read','Write','Bash','CodexFileChange'])assert.equal((await p.approvalHook({tool_name:tool,tool_input:{command:'ls',file_path:'/tmp/file'},cwd:'/tmp'})).hookSpecificOutput.permissionDecision,'allow');
 const claude=p.protectConfig({provider:'claude',model:'claude-opus-5-5',thinkingOptionId:'medium',cwd:'/tmp'});
 assert.equal(claude.modeId,'bypassPermissions');assert.equal(claude.featureValues.auto_accept,true);
 const codex=p.protectConfig({provider:'codex',model:'gpt-6.1-sol',thinkingOptionId:'low',cwd:'/tmp'});
 assert.equal(codex.providerOptions.approval_policy,'never');assert.equal(codex.providerOptions.sandbox_mode,'danger-full-access');
 assert.equal(p.protectConfig({provider:'grok',model:'grok-4.7',thinkingOptionId:'high',cwd:'/tmp'}).modeId,'bypassPermissions');
 assert.throws(()=>p.assertModelAllowed('codex','gpt-6-astra'));
 assert.throws(()=>p.assertModelAllowed('grok','grok-5'));
 assert.throws(()=>p.assertThinkingAllowed('ultra'));
 assert.throws(()=>p.protectConfig({provider:'grok',model:'grok-4.7',thinkingOptionId:'medium',cwd:'/tmp'}));
 const session={provider:'codex',setModel(value){return value},setFeature(name,value){return value}};
 p.installSessionPolicy(session);assert.equal(session.setFeature('auto_accept',true),true);
 assert.throws(()=>session.setModel('gpt-6-astra'));assert.throws(()=>session.setFeature('xhigh',true));
 class FakeClaude {constructor(){this.config={internal:false}} async buildOptions(){return {permissionMode:'acceptEdits'}}}
 p.installClaudePolicy(FakeClaude);const options=await new FakeClaude().buildOptions();
 assert.equal(options.permissionMode,'bypassPermissions');assert.equal(options.allowDangerouslySkipPermissions,true);
 console.log('Comandos e edições livres; modos Claude/Codex/Grok e limites de modelos/esforço verificados.');
} finally {rmSync(dir,{recursive:true,force:true});}
