import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, cp, symlink, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {stagedLaunch} from '../../native/staged-launch.mjs';
const root=resolve(import.meta.dirname,'../..');
async function receiver(t) {
 const temp=await mkdtemp(join(tmpdir(),'paseo-receiver-'));t.after(()=>rm(temp,{recursive:true,force:true}));
 await mkdir(join(temp,'message-receipts'));
 await cp(join(root,'installed-paseo/server/dist/server/server/message-receipts/index.js'),join(temp,'message-receipts/index.mjs'));
 await cp(join(root,'installed-paseo/server/dist/server/server/atomic-file.js'),join(temp,'atomic-file.js'));
 await symlink(join(root,'tests/native-deps/node_modules'),join(temp,'node_modules'),'dir');
 const {MessageReceipts}=await import(pathToFileURL(join(temp,'message-receipts/index.mjs')));
 return {MessageReceipts,directory:join(temp,'receipts')};
}
test('lost response / receiver restart / same UUID executes once',async t=>{
 const {MessageReceipts,directory}=await receiver(t);let calls=0;
 const input={agentId:'agent',messageId:'logical-message',request:{prompt:'work'},send:async()=>{calls++;}};
 await new MessageReceipts(directory).send(input);
 // Caller did not receive the response. Receiver has restarted before replay.
 await new MessageReceipts(directory).send(input);assert.equal(calls,1);
});
test('ambiguous provider outcome cannot be bypassed by replay',async t=>{
 const {MessageReceipts,directory}=await receiver(t);let calls=0;
 const input={agentId:'agent',messageId:'logical-message',request:{prompt:'work'},send:async()=>{calls++;throw Error('crash after provider accepted');}};
 await assert.rejects(new MessageReceipts(directory).send(input),/crash/);
 await assert.rejects(new MessageReceipts(directory).send(input),/outcome_unknown/);assert.equal(calls,1);
});
test('parallel delivery of the same message is serialized',async t=>{
 const {MessageReceipts,directory}=await receiver(t);const receipts=new MessageReceipts(directory);let calls=0;
 const input={agentId:'agent',messageId:'parallel',request:{prompt:'work'},send:async()=>{calls++;}};
 await Promise.all([receipts.send(input),receipts.send(input)]);assert.equal(calls,1);
});
test('controller staged launch replays create and send after a lost reply',async t=>{
 const {MessageReceipts,directory}=await receiver(t);const receipts=new MessageReceipts(directory);let inference=0;let lost=true;
 const agentId='11111111-1111-4111-a111-111111111111';let creations=new Set();
 const client={
  createAgent:async options=>{creations.add(options.agentId);return {id:options.agentId};},
  fetchAgentTimeline:async()=>({entries:[]}),
  sendMessage:async(id,prompt,options)=>{await receipts.send({agentId:id,messageId:options.messageId,request:{prompt},send:async()=>{inference++;}});if(lost){lost=false;throw Error('reply lost');}return {accepted:true};}
 };
 const options={agentId,idempotencyKey:'same-task-attempt',initialPrompt:'implement task'};
 await assert.rejects(stagedLaunch(client,options),/reply lost/);await stagedLaunch(client,options);
 assert.equal(inference,1);assert.equal(creations.size,1);
});
