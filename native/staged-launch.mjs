import { createHash } from 'node:crypto';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function messageIdFor(requestId) {
  const hex = createHash('sha256').update(String(requestId)).digest('hex');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
}

function timelineHas(timeline, messageId) {
  return (timeline?.entries || []).some(entry => {
    const item=entry.item || {};
    return item.type==='user_message' && (item.clientMessageId || item.messageId)===messageId && Boolean(entry.providerMessageId || item.providerMessageId);
  });
}

export async function stagedLaunch(client, options) {
  const expected = options.agentId;
  if (expected && !UUID_RE.test(expected)) throw new Error('agentId must be a UUID');
  const createOptions = { ...options };
  delete createOptions.initialPrompt;
  delete createOptions.admissionTicket;
  delete createOptions.initialPromptReceived;
  let result;
  if (expected && client.fetchAgent) {
    try {
      const existing = await client.fetchAgent(expected);
      if (existing) {
        const a = existing.agent || existing;
        if (a?.id !== expected || a.provider !== options.provider || a.model !== options.model || a.cwd !== options.cwd)
          throw new Error('Existing staged identity differs from the authorized request');
        result = existing;
      }
    } catch(error) {
      if (!(error.code === 'agent_not_found' || /agent.*not found/i.test(error.message || ''))) throw error;
    }
  }
  if (!result) result = await client.createAgent(createOptions);
  const created = result?.agent || result;
  const agentId = created?.id || created?.agentId;
  if (expected && agentId !== expected) throw new Error('agent id diverges from the preassigned id');
  const requestId = options.idempotencyKey || options.requestId || expected;
  const messageId = messageIdFor(requestId);
  let already = options.initialPromptReceived === true;
  if (!already && agentId && options.initialPrompt && client.fetchAgentTimeline) {
    try {
      const timeline = await client.fetchAgentTimeline(agentId, { limit: 80, projection: 'canonical' });
      already = timelineHas(timeline, messageId);
    } catch {
      already = false;
    }
  }
  if (options.initialPrompt && agentId && !already) {
    const sent = await client.sendMessage(agentId, options.initialPrompt, { messageId, activeTurnBehavior: 'steer' });
    return { ...result, agentId, initialPromptReceipt: messageId, send: sent };
  }
  return { ...result, agentId, initialPromptReceipt: messageId, initialPromptSkipped: Boolean(options.initialPrompt) };
}
