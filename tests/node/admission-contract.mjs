import assert from 'node:assert/strict';
import fs from 'node:fs';
import {assertTurnAdmission, protectConfig, unrestrictedTools} from '../../policy/policy.mjs';
const f=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
assert.equal(assertTurnAdmission(f.agent,'codex','gpt-6.1-terra','medium'),'admitted');
assert.throws(()=>assertTurnAdmission(f.agent,'codex','gpt-6.1-terra','high'),/Esforço/);
assert.throws(()=>assertTurnAdmission(f.agent,'codex','gpt-6.1-sol','medium'),/Modelo/);
const worker={agentId:f.agent,provider:'codex',model:'gpt-6.1-terra',thinkingOptionId:'medium',cwd:f.cwd};
assert.equal(unrestrictedTools(worker),false);
assert.equal(protectConfig(worker).providerOptions.approval_policy,'never');
assert.equal(unrestrictedTools({agentId:'manager-fixture'}),true);
// A similarly named worker cannot claim root by setting a role string.
assert.equal(unrestrictedTools({...worker,role:'manager'}),false);
console.log('signed ticket / held lease / native gate / bounded effort / role-scoped tools: OK');
