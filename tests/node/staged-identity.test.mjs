import test from 'node:test';
import assert from 'node:assert/strict';
import {stagedLaunch} from '../../native/staged-launch.mjs';
const id='12345678-1234-4123-a123-123456789abc';
const options={agentId:id,provider:'codex',model:'gpt-6.1-sol',cwd:'/tmp/dev'};
test('existing identity never creates another workspace',async()=>{
 let creates=0;
 const result=await stagedLaunch({fetchAgent:async()=>({agent:{id,provider:options.provider,model:options.model,cwd:options.cwd}}),createAgent:async()=>{creates++}},options);
 assert.equal(result.agentId,id);assert.equal(creates,0);
});
test('missing identity creates once',async()=>{
 let creates=0;
 const result=await stagedLaunch({fetchAgent:async()=>null,createAgent:async()=>{creates++;return {agent:{id}}}},options);
 assert.equal(result.agentId,id);assert.equal(creates,1);
});
test('transport uncertainty never means missing',async()=>{
 let creates=0;
 await assert.rejects(stagedLaunch({fetchAgent:async()=>{throw new Error('transport timeout')},createAgent:async()=>{creates++}},options),/timeout/);
 assert.equal(creates,0);
});
