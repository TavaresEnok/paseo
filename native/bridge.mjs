#!/usr/bin/env node
/** Paseo 0.13.2 native SDK bridge. JSON on stdin, JSON on stdout. */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { connectToDaemon } from '/home/enok/.local/share/node24/lib/node_modules/@getpaseo/cli/dist/utils/client.js';
import { stagedLaunch } from './staged-launch.mjs';

const input = JSON.parse(readFileSync(0, 'utf8') || '{}');
const home = input.home || '/home/enok/srv_projetos';
const action = input.action || 'inventory';
const redact = value => {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k,
    /^(password|token|accessToken|refreshToken|apiKey|secret|authorization|headers|env|email|accountId|organizationId|orgId)$/i.test(k) ? '[redacted]' : redact(v)]));
  if (typeof value === 'string') return value.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[account-email-redacted]');
  return value;
};
let client;
try {
  client = await connectToDaemon({ target: { kind: 'instance', home }, timeout: input.timeout || 30000 });
  let result;
  switch (action) {
    case 'inventory': {
      const config = (await client.getDaemonConfig()).config;
      const providers = await client.listAvailableProviders();
      const catalogs = {};
      await Promise.all((input.providers || ['claude', 'codex', 'codex-programmer', 'grok', 'antigravity2']).map(async provider => {
        try { let timer;
          try { catalogs[provider] = await Promise.race([client.listProviderModels(provider, { cwd: input.cwd || '/home/enok/Documentos/projetos' }),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Provider discovery timed out after 15s')),15000);timer.unref?.();})]); } finally { if(timer)clearTimeout(timer); } }
        catch (error) { catalogs[provider] = { error: error.message || String(error) }; }
      }));
      result = {
        fetchedAt: new Date().toISOString(), providers, catalogs,
        profiles: config.agentProfiles || [],
        orchestration: { mcp: config.mcp, providers: Object.fromEntries(Object.entries(config.providers || {}).map(([id,v]) => [id, { enabled: v.enabled, paseoTools: v.paseoTools }])) },
        skills: await client.getAgentSkillsStatus(),
      };
      break;
    }
    case 'message-receipt': {
      if (!input.agentId || !input.messageId) throw new Error('agentId e messageId obrigatórios');
      const key=createHash('sha256').update(JSON.stringify(['send',input.agentId,input.messageId])).digest('hex');
      try {
        const receipt=JSON.parse(readFileSync(join(home,'agent-requests',key+'.json'),'utf8'));
        if (receipt.agentId !== input.agentId || !['pending','completed'].includes(receipt.state)) throw new Error('Recibo inválido');
        result={state:receipt.state};
      } catch(error) {
        if (error.code==='ENOENT') result={state:'missing'};
        else throw error;
      }
      break;
    }
    case 'usage': result = await client.listUsageReports({ forceRefresh: input.refresh !== false }); break;
    case 'models': result = await client.listProviderModels(input.provider, { cwd: input.cwd }); break;
    case 'modes': result = await client.listProviderModes(input.provider, { cwd: input.cwd }); break;
    case 'providers': result = await client.listAvailableProviders(); break;
    case 'features': result = await client.listProviderFeatures(input.config); break;
    case 'skills-status': result = await client.getAgentSkillsStatus(); break;
    case 'skills-install': result = await client.saveAgentSkillsSelection({ mode: 'custom', skills: input.skills || ['paseo','paseo-handoff','paseo-committee','paseo-advisor'] }); break;
    case 'profiles': result = (await client.getDaemonConfig()).config.agentProfiles || []; break;
    case 'profiles-save': {
      const { AgentProfileSchema } = await import('/home/enok/.local/share/node24/lib/node_modules/@getpaseo/cli/node_modules/@getpaseo/protocol/dist/agent-profile.js');
      const profiles = input.profiles.map(profile => AgentProfileSchema.parse(profile));
      const old = (await client.getDaemonConfig()).config.agentProfiles || [];
      const byId = new Map(old.map(profile => [profile.id, profile]));
      for (const profile of profiles) byId.set(profile.id, profile);
      result = (await client.patchDaemonConfig({ agentProfiles: [...byId.values()] })).config.agentProfiles;
      break;
    }
    case 'patch-config': {
      if (!input.patch || typeof input.patch !== 'object') throw new Error('patch is required');
      const changed = await client.patchDaemonConfig(input.patch);
      result = { updated: true, profiles: changed.config.agentProfiles || [], mcp: changed.config.mcp };
      break;
    }
    case 'agents': result = await client.fetchAgents(input.options || {}); break;
    case 'agent': result = await client.fetchAgent(input.agentId); break;
    case 'timeline': result = await client.fetchAgentTimeline(input.agentId, input.options || {}); break;
    case 'wait': result = await client.waitForFinish(input.agentId, input.waitTimeoutMs ?? 60000); break;
    case 'workspace-create': result = await client.createWorkspace(input.options); break;
    case 'staged-launch': {
      const options = { ...input.options };
      if (!options.cwd && !options.config?.cwd && options.workspaceId) {
        const response = await client.fetchWorkspaces({});
        const workspace = response.entries?.find(item => item.id === options.workspaceId);
        if (!workspace?.workspaceDirectory) throw new Error('Cannot resolve workspace cwd for createAgent');
        options.cwd = workspace.workspaceDirectory;
      }
      result = await stagedLaunch(client, options);
      break;
    }
    case 'agent-create': {
      const options = { ...input.options };
      if (!options.cwd && !options.config?.cwd && options.workspaceId) {
        const response = await client.fetchWorkspaces({});
        const workspace = response.entries?.find(item => item.id === options.workspaceId);
        if (!workspace?.workspaceDirectory) throw new Error('Cannot resolve workspace cwd for createAgent');
        options.cwd = workspace.workspaceDirectory;
      }
      result = await client.createAgent(options); break;
    }
    case 'send': result = await client.sendMessage(input.agentId, input.prompt, input.options || {}); break;
    case 'stop': await client.cancelAgent(input.agentId); result = { stopped: true }; break;
    case 'permit': await client.respondToPermissionAndWait(input.agentId, input.requestId, input.response); result = { responded: true }; break;
    case 'archive': result = await client.archiveAgent(input.agentId); break;
    case 'project-add': result = await client.addProject(input.cwd); break;
    case 'workspaces': result = await client.fetchWorkspaces(input.options || {}); break;
    case 'workspace-archive': result = await client.archiveWorkspace(input.workspaceId); break;
    case 'workspace-title': result = await client.setWorkspaceTitle(input.workspaceId, input.title); break;
    case 'workspace-pin': result = await client.setWorkspacePinned(input.workspaceId, input.pinned); break;
    case 'projects': result = await client.listProjects(); break;
    case 'project-remove': result = await client.removeProject(input.projectId); break;
    default: throw new Error(`Unsupported action: ${action}`);
  }
  const output = redact(result);
  if (input.output) writeFileSync(input.output, JSON.stringify(output, null, 2) + '\n', { mode: 0o600 });
  process.stdout.write(JSON.stringify(input.output ? { saved: input.output } : output) + '\n');
} catch (error) {
  process.stdout.write(JSON.stringify({ error: error.message || String(error), code: error.code || null }) + '\n');
  process.exitCode = 1;
} finally {
  await client?.close();
}
