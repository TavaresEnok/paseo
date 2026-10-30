import { createHmac } from 'node:crypto';
import { readFileSync, appendFileSync, realpathSync, existsSync, lstatSync, readlinkSync } from 'node:fs';
import { resolve, dirname, relative, isAbsolute } from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const POLICY_FILE = process.env.PASEO_POLICY_FILE || '/home/enok/srv_projetos/config/profiles.json';
const AUDIT_FILE = process.env.PASEO_POLICY_AUDIT || '/home/enok/srv_projetos/logs/policy.jsonl';
const PROVIDERS = new Set(['codex-programmer', 'claude', 'codex', 'opencode', 'grok', 'antigravity', 'antigravity2', 'antigravity3']);
const ROOTS = (process.env.PASEO_POLICY_ROOTS || '/home/enok/srv_projetos/workspace:/home/enok/srv_projetos/worktrees').split(':');
const READ_TOOLS = new Set(['Read', 'Glob', 'Grep', 'LS', 'ToolSearch', 'TodoRead', 'TodoWrite', 'AskUserQuestion']);
const EDIT_TOOLS = new Set(['Write', 'Edit', 'MultiEdit', 'NotebookEdit']);
const INSTALLED = Symbol.for('paseo.localPolicy.v2');
const SESSION_GUARDED = Symbol.for('paseo.localPolicy.session.v2');
const HOST_DEFAULTS = {
  admissionDb: '/home/enok/srv_projetos/orchestration/admission.sqlite3',
  tokenFile: '/home/enok/srv_projetos/config/account-capacity.token',
  modelLimits: '/home/enok/srv_projetos/config/model-limits.json',
  billing: '/home/enok/srv_projetos/orchestration/evidence/grok-billing.json',
  flowDb: '/home/enok/srv_projetos/orchestration/state.sqlite3',
};
const MODEL_LIMITS_FILE = process.env.PASEO_MODEL_LIMITS || HOST_DEFAULTS.modelLimits;
function admissionDb() { return process.env.PASEO_ADMISSION_DB || HOST_DEFAULTS.admissionDb; }
function capacityTokenFile() { return process.env.PASEO_CAPACITY_TOKEN_FILE || HOST_DEFAULTS.tokenFile; }
function billingFile() { return process.env.PASEO_GROK_BILLING || HOST_DEFAULTS.billing; }
function flowDb() { return process.env.PASEO_FLOW_DB || HOST_DEFAULTS.flowDb; }
export function readModelLimits() { return JSON.parse(readFileSync(MODEL_LIMITS_FILE, 'utf8')); }
export function assertModelAllowed(provider, model) {
  const limits = readModelLimits();
  if (provider === 'opencode' && limits.grok.transport === 'grok-cli')
    throw new Error('OpenCode desativado: usar exclusivamente o CLI oficial Grok 4.7 Médio.');
  const resolved = model ?? (provider === 'codex' ? limits.codex.default_model : null);
  if (resolved && limits.forbidden_model_fragments.some(part => resolved.toLowerCase().includes(part.toLowerCase())))
    throw new Error('Modelo Astra proibido pela política explícita do usuário.');
  if (provider === 'codex-programmer' && !(limits.programmer_account?.enabled && resolved === 'gpt-6.1-terra')) throw new Error('Conta programador permite somente GPT-6.1 Terra.');
  if (provider === 'codex' && !limits.codex.allowed_models.includes(resolved))
    throw new Error('Codex limitado a GPT-6.1 Sol, GPT-6 Luna e GPT-5.6 Terra.');
  if (provider === 'opencode' && resolved !== 'xai/grok-4.7')
    throw new Error('OpenCode permite exclusivamente Grok 4.7 Médio; GLM e outros modelos proibidos.');
  if (resolved && (['grok', 'xai'].includes(provider) || /grok|^xai\//i.test(resolved))) {
    const required = 'grok-' + (limits.grok.required_version ?? '4.7');
    if (resolved.split('/').at(-1).toLowerCase() !== required || !limits.grok.allowed_models.includes(resolved))
      throw new Error('Somente Grok 4.7 é permitido, após validar o login da assinatura e o ID real.');
    let proof;
    try { proof = JSON.parse(readFileSync(billingFile(),'utf8')); }
    catch { throw new Error('Grok bloqueado: verificação da assinatura indisponível.'); }
    const age = Date.now() - Date.parse(proof.timestamp_utc);
    const billing = proof.results?.billing ?? {};
    const topup = proof.results?.auto_topup ?? {};
    if (!(age >= 0 && age <= 300000 && proof.subscription_only_evidence === true &&
        billing.http_status === 200 && billing.unified_billing === true && billing.remaining_percent > 0 &&
        billing.prepaid_cents === 0 && (billing.on_demand_cap_cents == null || billing.on_demand_cap_cents === 0) &&
        billing.on_demand_enabled !== true && topup.http_status === 200 && topup.enabled === false &&
        (provider !== 'grok' || proof.credential_source === 'grok_cli')))
      throw new Error('Grok bloqueado: franquia/custo zero não verificado ou informação vencida.');
  }
  if (['antigravity','antigravity2','antigravity3'].includes(provider) && !(limits.gemini?.enabled && (!limits.gemini.enabled_provider_ids || limits.gemini.enabled_provider_ids.includes(provider)) && (limits.gemini.allowed_models.includes(resolved) || (provider === 'antigravity2' && limits.antigravity_sonnet?.enabled && resolved === 'claude-sonnet-5-5-medium')))) throw new Error('Modelo Antigravity fora da política aprovada.');
  return resolved;
}
export function assertThinkingAllowed(value) {
  if (value != null && !readModelLimits().allowed_thinking_options.includes(value))
    throw new Error('Esforço acima de Alto ou desconhecido bloqueado. Nunca usar xhigh, max ou ultra.');
  return value;
}
function canonicalTicket(ticket) {
  const payload = {};
  for (const key of ['agent_id', 'chat_id', 'cwd', 'decision_fp', 'effort', 'model', 'provider', 'request_id', 'role', 'v']) payload[key] = ticket[key] ?? null;
  payload.v = 1;
  const ordered = {};
  for (const key of Object.keys(payload).sort()) ordered[key] = payload[key];
  return JSON.stringify(ordered);
}
function readAdmission(agentId) {
  const dbPath = admissionDb();
  if (!dbPath || !agentId) return null;
  const script = [
    'import json,sqlite3,sys',
    'db=sqlite3.connect(sys.argv[1])',
    'row=db.execute("SELECT ticket_json FROM tickets WHERE agent_id=?", (sys.argv[2],)).fetchone()',
    'print(row[0] if row and row[0] else "")',
  ].join('\n');
  try {
    const out = execFileSync('python3', ['-c', script, dbPath, String(agentId)], { encoding: 'utf8', timeout: 2000 });
    return out.trim() ? JSON.parse(out) : null;
  } catch { return null; }
}
function currentFingerprint(chatId, role) {
  if (!chatId || !role) return null;
  const script = [
    'import sqlite3,sys',
    'db=sqlite3.connect(sys.argv[1])',
    'row=db.execute("SELECT fingerprint FROM current_decisions WHERE chat_id=? AND role=?", (sys.argv[2], sys.argv[3])).fetchone()',
    'print(row[0] if row else "")',
  ].join('\n');
  try {
    const out = execFileSync('python3', ['-c', script, admissionDb(), String(chatId), String(role)], { encoding: 'utf8', timeout: 2000 });
    return out.trim() || null;
  } catch { return null; }
}
export function verifiedAdmission(agentId) {
  const tokenFile = capacityTokenFile();
  if (!tokenFile) return null;
  let token;
  try { token = readFileSync(tokenFile, 'utf8').trim(); } catch { return null; }
  const ticket = readAdmission(agentId);
  if (!token || !ticket?.mac) return null;
  const expected = createHmac('sha256', token).update(canonicalTicket(ticket)).digest('hex');
  if (expected !== ticket.mac) return null;
  return ticket;
}
export function assertTurnAdmission(agentId, provider, requestedModel, requestedEffort) {
  let limits;
  try { limits = readModelLimits(); } catch { return 'legacy'; }
  if (limits.policy_engine !== 'proposed-2026-10-29') return 'legacy';
  const ticket = verifiedAdmission(agentId);
  if (!ticket) return 'none';
  if (ticket.agent_id && agentId && ticket.agent_id !== agentId) throw new Error('Ticket não pertence a este agente.');
  if (provider && ticket.provider && provider !== ticket.provider) throw new Error('Provedor não confere com o ticket do controlador.');
  if (requestedModel && requestedModel !== ticket.model) throw new Error('Modelo não confere com o ticket do controlador.');
  const adaptiveManager = ticket.role === 'manager' && ticket.provider === 'codex' && ticket.model === 'gpt-6.1-sol' && limits.supervision?.adaptive_effort?.enabled === true && ['medium','high'].includes(ticket.effort) && ['medium','high'].includes(requestedEffort);
  if (requestedEffort && requestedEffort !== ticket.effort && !adaptiveManager) throw new Error('Esforço não confere com o ticket do controlador.');
  if (['programmer', 'reviewer'].includes(ticket.role)) {
    const holdPath=process.env.PASEO_HOLD_FILE || '/home/enok/srv_projetos/orchestration/OPERATOR-HOLD.json';
    if (existsSync(holdPath) && JSON.parse(readFileSync(holdPath,'utf8')).active !== false) throw new Error('Pausa global explícita: não iniciar trabalhador.');
    if (!heldWorkerLease(ticket)) throw new Error('Ticket worker sem lease local held/uncertain vinculada.');
  } else {
    const current = currentFingerprint(ticket.chat_id, ticket.role);
    if (!current || current !== ticket.decision_fp) throw new Error('Decisão vigente não confere com o ticket.');
  }
  const model = String(ticket.model || '');
  if (model.toLowerCase().includes('astra')) {
    if (ticket.role !== 'manager' || ticket.effort !== 'medium' || !model.endsWith('gpt-6-astra') || ticket.provider !== 'codex')
      throw new Error('Astra somente gerente médio com ticket do controlador.');
    return 'astra';
  }
  if ((provider === 'grok' || ticket.provider === 'grok') && ticket.role === 'reviewer' && ticket.effort !== 'high')
    throw new Error('Revisão Grok exige esforço high no ticket.');
  if ((provider === 'grok' || ticket.provider === 'grok') && ticket.role === 'programmer' && ticket.effort !== 'medium')
    throw new Error('Programação Grok exige esforço medium no ticket.');
  if ((provider === 'grok' || ticket.provider === 'grok') && !['programmer', 'reviewer'].includes(ticket.role))
    throw new Error('Grok não é gerente nesta política.');
  if (['antigravity','antigravity2','antigravity3'].includes(ticket.provider) && (ticket.role !== 'programmer' || !((ticket.model === 'gemini-3.8-flash-high' && ticket.effort === 'high') || (ticket.provider === 'antigravity2' && readModelLimits().antigravity_sonnet?.enabled && ticket.model === 'claude-sonnet-5-5-medium' && ticket.effort === 'medium')))) throw new Error('Antigravity somente programador Flash Alto ou Sonnet Médio.');
  if (ticket.provider === 'codex-programmer' && (ticket.role !== 'programmer' || ticket.model !== 'gpt-6.1-terra' || ticket.effort !== 'medium')) throw new Error('Conta Codex dedicada somente programador Terra Médio.');
  return 'admitted';
}
function heldWorkerLease(ticket) {
  const script = `import sqlite3,sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True) as db:
 row=db.execute("SELECT 1 FROM capacity_leases WHERE agent_id=? AND request_id=? AND role=? AND chat_id=? AND status IN ('held','uncertain')",sys.argv[2:]).fetchone()
 print('yes' if row else '')`;
  try {
    return execFileSync('python3', ['-c', script, flowDb(), ticket.agent_id, ticket.request_id, ticket.role, ticket.chat_id],
      { encoding: 'utf8', timeout: 2000, stdio: ['ignore','pipe','pipe'] }).trim() === 'yes';
  } catch { return false; }
}
function isManagerRoot(cwd) {
  if (typeof cwd !== "string" || !cwd) return false;
  const path = canonical(cwd);
  const projects = canonical('/home/enok/Documentos/projetos');
  return path === canonical(ROOTS[0]) || path === projects || path.startsWith(projects + '/');
}
function managerConfig(config = {}) {
  const labels = config.labels || {};
  const role = labels['flow.role'] || config.env?.PASEO_FLOW_ROLE || config.role;
  if ([labels['flow.role'], config.env?.PASEO_FLOW_ROLE, config.role].some(value => ['programmer','reviewer'].includes(value))) return false;
  const ticket = verifiedAdmission(config.policyAgentId || config.agentId || config.env?.PASEO_AGENT_ID);
  if (ticket && ['programmer', 'reviewer'].includes(ticket.role)) return false;
  if (ticket?.role === 'manager') return true;
  const profile = String(config.profileId || config.agentProfileId || '');
  if (role === 'supervisor' || role === 'manager' || profile.includes('supervisor')) return true;
  const model = String(config.model || '');
  const effort = config.thinkingOptionId || config.effort;
  if (config.provider === 'codex' && model === 'gpt-6.1-sol' && effort === 'high' && isManagerRoot(config.cwd)) return true;

  return false;
}
function guardUnticketed(config, mark) {
  if (mark !== 'none') return;
  if (managerConfig(config)) {
    if (String(config.model || '').toLowerCase().includes('astra')) throw new Error('Astra somente com ticket de emergência.');
    return;
  }
  throw new Error('Trabalhador sem ticket do controlador.');
}
function assertCurrentOwner(agentId, config = {}) {
  if (!managerConfig(config)) return;
  const chat = verifiedAdmission(agentId)?.chat_id || config.labels?.['flow.chat'] || config.env?.PASEO_FLOW_CHAT;
  if (!agentId) return;
  const script = [
    'import sqlite3,sys',
    'db=sqlite3.connect(sys.argv[1])',
    'tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type=\'table\'")}',
    'route=db.execute("SELECT primary_id,active_id FROM supervisor_routes WHERE ? IN (primary_id,active_id,fallback_id) AND state!=\'superseded\' ORDER BY updated DESC LIMIT 1", (sys.argv[3],)).fetchone() if "supervisor_routes" in tables else None',
    'chat=sys.argv[2] or (route[0] if route else "")',
    'owner=db.execute("SELECT agent_id FROM manager_owners WHERE chat_id=?", (chat,)).fetchone() if "manager_owners" in tables else None',
    'if owner: print(owner[0]); sys.exit(0)',
    'if route: print(route[1]); sys.exit(0)',
    'row=db.execute("SELECT jobs.supervisor_id FROM jobs LEFT JOIN policy_job_chats ON policy_job_chats.job_id=jobs.id WHERE COALESCE(policy_job_chats.chat_id, jobs.supervisor_id)=? AND jobs.state NOT IN (\'paused\',\'canceled\',\'cancelled\') ORDER BY jobs.updated DESC LIMIT 1", (sys.argv[2],)).fetchone()',
    'print(row[0] if row else "")',
  ].join('\n');
  try {
    const owner = execFileSync('python3', ['-c', script, flowDb(), String(chat || ''), String(agentId)], { encoding: 'utf8', timeout: 2000 }).trim();
    if ((owner && owner !== agentId) || (!owner && verifiedAdmission(agentId)?.role === 'manager')) throw new Error('Gerente ocioso não admite turno sem ser o dono vigente.');
  } catch (error) {
    if (String(error.message || error).includes('Gerente ocioso')) throw error;
    if (verifiedAdmission(agentId)?.role === 'manager') throw new Error('Gerente sem registro de dono verificável.');
  }
}
function currentPolicyText() {
  const script="import sys;sys.path.insert(0,'/home/enok/.local/share/paseo-orchestrator');from orchestrator.model_limits import role_summary;print(role_summary())";
  return execFileSync('/home/enok/.local/bin/python3.12',['-c',script],{encoding:'utf8',timeout:3000}).trim();
}

export function applyCurrentPolicy(target) {
  if (!target || typeof target !== 'object') return target;
  const marker = 'POLÍTICA VIGENTE DO CONTROLADOR';
  const end = '[FIM PASEO_POLICY_V2]';
  const block = marker + '\n' + currentPolicyText() + '\n' + end;
  const renew = value => {
    let text = String(value || '');
    const obsolete = /^(POLÍTICA VIGENTE \(model-limits\):|POLÍTICA OBRIGATÓRIA DE CONSUMO:|Programação exclusivamente |Toda programação exclusivamente |A implementação usa o CLI oficial Grok|Transporte exclusivamente pelo CLI oficial Grok|Gerente principal:|Gerente substituto:|Revisor principal:|Revisor substituto:|Revisão principal:|Programação principal:|Não escale para Astra,)/;
    text = text.split('\n').filter(line => !obsolete.test(line.trim())).join('\n');

    const begin = text.indexOf(marker);
    if (begin >= 0) {
      const finish = text.indexOf(end, begin);
      if (finish >= 0) text = text.slice(0, begin) + text.slice(finish + end.length);
      else {
        const lines = text.slice(begin + marker.length).replace(/^\n/, '').split('\n');
        while (lines.length && /^(Gerente |Programação |Revisão |Grok padrão |Conta compartilhada:)/.test(lines[0])) lines.shift();
        text = text.slice(0, begin) + lines.join('\n');
      }
    }
    return block + (text.trim() ? '\n\n' + text.trim() : '');
  };
  target.systemPrompt = renew(target.systemPrompt);
  target.appendSystemPrompt = renew(target.appendSystemPrompt);
  return target;
}
function defaultThinking(provider) { return ['opencode','grok'].includes(provider) ? 'medium' : 'medium'; }
function assertProviderThinking(provider, value) {
  assertThinkingAllowed(value);
  if (['opencode','grok'].includes(provider) && (value ?? defaultThinking(provider)) !== 'medium')
    throw new Error('OpenCode permite exclusivamente Grok 4.7 com esforço Médio/medium.');
}
function autonomyConfig() {
  try { return JSON.parse(readFileSync(process.env.PASEO_AUTONOMY_FILE || '/home/enok/srv_projetos/config/autonomy.json','utf8')); }
  catch { return {}; }
}
function roleTicket(config={}) { return verifiedAdmission(config.policyAgentId || config.agentId || config.env?.PASEO_AGENT_ID); }
export function unrestrictedTools(config={}) {
  const autonomy=autonomyConfig();
  if (!autonomy.role_scoped_tools) return autonomy.unrestricted_tools===true;
  return autonomy.manager_unrestricted_tools===true && roleTicket(config)?.role==='manager';
}
function workerTools(config={}) {
  return autonomyConfig().worker_unattended_tools===true && ['programmer','reviewer'].includes(roleTicket(config)?.role);
}
function unattendedDevelopment(cwd) {
  try {
    return isDevelopmentPath(cwd) && JSON.parse(readFileSync('/home/enok/srv_projetos/config/autonomy.json','utf8')).unattended_development === true;
  } catch { return false; }
}
const SAFE_PASEO = new Set(['list_profiles', 'list_providers', 'list_models', 'inspect_provider',
  'create_agent', 'get_agent_status', 'send_agent_prompt', 'list_agents', 'list_workspaces',
  'create_workspace', 'get_workspace', 'get_agent_timeline', 'get_agent', 'wait_for_agent']);

export function readPolicy() {
  const policy = JSON.parse(readFileSync(POLICY_FILE, 'utf8'));
  if (!Number.isSafeInteger(policy.max_concurrent_executors) || policy.max_concurrent_executors < 1)
    throw new Error('Política inválida: max_concurrent_executors deve ser um inteiro positivo.');
  return policy;
}
function audit(event, details = {}) {
  appendFileSync(AUDIT_FILE, JSON.stringify({ at: new Date().toISOString(), event, ...details }) + '\n', { mode: 0o600 });
}
function canonical(path) {
  const absolute = resolve(path);
  try {
    if (lstatSync(absolute).isSymbolicLink()) return canonical(resolve(dirname(absolute), readlinkSync(absolute)));
  } catch (error) {
    if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') throw error;
  }
  if (existsSync(absolute)) return realpathSync(absolute);
  const parent = dirname(absolute);
  if (parent === absolute) return absolute;
  return resolve(canonical(parent), relative(parent, absolute));
}
export function isDevelopmentPath(path, cwd = ROOTS[0]) {
  if (typeof path !== 'string' || !path) return false;
  const target = canonical(resolve(cwd, path));
  return ROOTS.some(root => {
    const rel = relative(canonical(root), target);
    return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel));
  });
}
function assertCwd(config) {
  if (!unrestrictedTools(config) && !config.internal && !isDevelopmentPath(config.cwd))
    throw new Error('Agentes executores só podem trabalhar em workspace/worktrees de desenvolvimento aprovadas.');
}

function admittedThinking(config, mark) {
  if (mark === 'astra') {
    if ((config.thinkingOptionId ?? 'medium') !== 'medium') throw new Error('Astra somente esforço medium.');
    return;
  }
  if (mark === 'admitted' && ['antigravity','antigravity2','antigravity3'].includes(config.provider)) {
    assertModelAllowed(config.provider, config.model);
    if (config.thinkingOptionId != null && config.thinkingOptionId !== (config.model === 'claude-sonnet-5-5-medium' ? 'medium' : 'high')) throw new Error('Esforço Antigravity divergente do modelo.');
    return;
  }
  if (mark === 'admitted' && config.provider === 'grok') {
    assertThinkingAllowed(config.thinkingOptionId);
    return;
  }
  assertModelAllowed(config.provider, config.model);
  assertProviderThinking(config.provider, config.thinkingOptionId);
}
export function protectConfig(config) {
  readPolicy();
  if (!PROVIDERS.has(config.provider)) throw new Error(`Provedor ${config.provider} sem política validada.`);
  assertCwd(config);
  const signed = verifiedAdmission(config.policyAgentId || config.agentId || config.env?.PASEO_AGENT_ID);
  if (signed?.cwd && canonical(signed.cwd) !== canonical(config.cwd)) throw new Error('Diretório não confere com o ticket.');
  const discovery = config.discovery === true || config.metadataOnly === true || config.purpose === 'model-metadata';
  if (discovery && config.provider === 'grok') {
    assertThinkingAllowed(config.thinkingOptionId);
  } else {
    const agentId = config.policyAgentId || config.agentId || config.env?.PASEO_AGENT_ID;
    let mark = 'legacy';
    try {
      if (readModelLimits().policy_engine === 'proposed-2026-10-29') mark = assertTurnAdmission(agentId, config.provider, config.model, config.thinkingOptionId);
    } catch (error) {
      if (!discovery) throw error;
    }
    if (!discovery) {
      guardUnticketed(config, mark);
      assertCurrentOwner(config.policyAgentId || config.agentId || config.env?.PASEO_AGENT_ID, config);
      admittedThinking(config, mark);
    }
  }
  const result = { ...config, thinkingOptionId: config.thinkingOptionId ?? defaultThinking(config.provider),
    featureValues: { ...config.featureValues, auto_accept: false } };
  if (config.provider === 'codex') result.model = config.model ?? readModelLimits().codex.default_model;
  for (const key of ['ultra', 'ultracode', 'xhigh']) if (result.featureValues[key])
    throw new Error('Esforço acima de Alto proibido pela política do usuário.');
  // Preserve the native Paseo MCP and its delegation policy. Managed child
  // agents pass through this same admission and cwd boundary.
  if (['codex','codex-programmer'].includes(config.provider)) {
    const readonly = config.internal || config.modeId === 'read-only';
    result.modeId = readonly ? 'read-only' : 'auto';
    result.providerOptions = { ...config.providerOptions, sandbox_mode: readonly ? 'read-only' : unattendedDevelopment(config.cwd) ? 'danger-full-access' : 'workspace-write',
      approval_policy: unattendedDevelopment(config.cwd) && !readonly ? 'never' : 'on-request',
      features: { ...config.providerOptions?.features, multi_agent_v2: false },
      sandbox_workspace_write: { ...config.providerOptions?.sandbox_workspace_write,
        writable_roots: [config.cwd], network_access: false, exclude_slash_tmp: true, exclude_tmpdir_env_var: true } };
  } else if (config.provider === 'claude') {
    result.modeId = config.internal || config.modeId === 'plan' ? 'plan' : 'acceptEdits';
    result.providerOptions = { ...config.providerOptions,
      disallowedTools: [...new Set([...(config.providerOptions?.disallowedTools ?? []), 'Agent', 'Task'])] };
  } else if (['antigravity','antigravity2','antigravity3'].includes(config.provider)) {
    result.modeId = 'full-access';
    delete result.thinkingOptionId;
  } else if (config.provider === 'grok') {
    result.modeId = config.internal || config.modeId === 'plan' ? 'plan' : 'bypassPermissions';
    result.providerOptions = { ...config.providerOptions, clientCapabilities: { fs: { readTextFile: false, writeTextFile: false }, terminal: false } };
  } else {
    result.modeId = config.internal || config.modeId === 'plan' ? 'plan' : 'build';
    result.providerOptions = { ...config.providerOptions, permission: {
      read: 'allow', glob: 'allow', grep: 'allow', list: 'allow',
      edit: config.internal ? 'ask' : 'allow',
      bash: { '*': unattendedDevelopment(config.cwd) && !config.internal ? 'allow' : 'ask', 'pwd': 'allow', 'ls*': 'allow', 'rg *': 'allow',
        'git status*': 'allow', 'git diff*': 'allow', 'git log*': 'allow', 'git show*': 'allow',
        'python3 -m pytest*': 'allow', 'python3 -m unittest*': 'allow', 'pytest*': 'allow',
        'node --test*': 'allow', 'npm test*': 'allow', 'npm run test*': 'allow',
        'npm run lint*': 'allow', 'npm run build*': 'allow', 'npm run typecheck*': 'allow',
        '*;*': unattendedDevelopment(config.cwd) ? 'allow' : 'ask', '*&&*': unattendedDevelopment(config.cwd) ? 'allow' : 'ask', '*||*': unattendedDevelopment(config.cwd) ? 'allow' : 'ask', '*|*': unattendedDevelopment(config.cwd) ? 'allow' : 'ask', '*`*': unattendedDevelopment(config.cwd) ? 'allow' : 'ask', '*$(*': unattendedDevelopment(config.cwd) ? 'allow' : 'ask',
        '*rm *': 'ask', '*git push*': 'ask', '*git merge*': 'ask', '*deploy*': 'ask',
        '*docker*': 'ask', '*systemctl*': 'ask', '*sudo*': 'ask', '*ssh*': 'ask', '*curl*': 'ask',
        '*wget*': 'ask', '*billing*': 'ask', '*payment*': 'ask', '*drop database*': 'ask', '*truncate*': 'ask' },
      task: 'deny', external_directory: 'ask', webfetch: 'ask', websearch: 'allow',
      repo_clone: 'ask', skill: 'allow', doom_loop: 'ask', question: 'allow', todowrite: 'allow',
    } };
  }
  if (config.provider === 'opencode' && unattendedDevelopment(config.cwd) && !config.internal) {
    const permissions = result.providerOptions.permission;
    // Protected commands fail back to the manager instead of opening a dialog.
    for (const [key,value] of Object.entries(permissions.bash)) if (value === 'ask') permissions.bash[key]='deny';
    permissions.external_directory='deny';
    permissions.webfetch='allow'; permissions.repo_clone='allow'; permissions.doom_loop='deny';
  }
  if ((unrestrictedTools(config) || workerTools(config)) && !config.internal) {
    result.featureValues.auto_accept = true;
    if (['codex','codex-programmer'].includes(config.provider)) {
      result.modeId = 'auto';
      result.providerOptions.sandbox_mode = 'danger-full-access';
      result.providerOptions.approval_policy = 'never';
    } else if (config.provider === 'claude') result.modeId = 'bypassPermissions';
    else if (config.provider === 'grok') result.modeId = 'bypassPermissions';
  }
  return result;
}

function busyIds(manager, exceptId, reservations = new Set()) {
  const busy = new Set(reservations);
  for (const agent of manager.agents.values()) {
    if (manager.runs.hasRun(agent.id) || agent.activeForegroundTurnId || agent.lifecycle === 'running') busy.add(agent.id);
  }
  busy.delete(exceptId);
  return busy;
}
export function activeChatCount() {
  if (process.env.PASEO_ACTIVE_CHATS) {
    const parsed = Number(process.env.PASEO_ACTIVE_CHATS);
    if (Number.isInteger(parsed) && parsed >= 1) return parsed;
  }
  const script = [
    'import sqlite3,sys',
    'db=sqlite3.connect(sys.argv[1])',
    'row=db.execute("SELECT COUNT(DISTINCT chat_id) FROM policy_job_chats").fetchone()',
    'print(row[0] if row and row[0] else 0)',
  ].join('\n');
  try {
    const out = execFileSync('python3', ['-c', script, flowDb()], { encoding: 'utf8', timeout: 2000 });
    const parsed = Number(out.trim());
    if (Number.isInteger(parsed) && parsed >= 1) return parsed;
  } catch { /* empty install */ }
  return 1;
}
export function executorLimit(policy = readPolicy()) {
  let limits;
  try { limits = readModelLimits(); } catch { return policy.max_concurrent_executors; }
  if (limits.policy_engine !== 'proposed-2026-10-29') return policy.max_concurrent_executors;
  const chats = activeChatCount();
  const per = Number(limits.workers_per_chat || 10);
  const managers = Number(limits.managers_per_chat || 1);
  return chats * per + chats * managers;
}
export function managerForNewChat(evidence = {}) {
  const status = name => evidence[name];
  if (status('claude') === 'exhausted' && status('grok') === 'exhausted' && status('codex') === 'available') {
    return { profileId: 'etapa2-supervisor-astra', provider: 'codex', model: 'gpt-6-astra', thinkingOptionId: 'medium', role: 'manager', parentProfileId: 'etapa2-supervisor' };
  }
  if (status('codex') === 'exhausted' && status('claude') === 'available') {
    return { profileId: 'etapa2-supervisor-fallback', provider: 'claude', model: 'claude-sonnet-5-5', thinkingOptionId: 'high', role: 'manager', parentProfileId: 'etapa2-supervisor' };
  }
  if (String(status('codex')) === 'available' || status('codex') !== 'exhausted') {
    return { profileId: 'etapa2-supervisor', provider: 'codex', model: 'gpt-6.1-sol', thinkingOptionId: readModelLimits().supervision?.primary_thinking || 'high', role: 'manager', parentProfileId: 'etapa2-supervisor' };
  }
  return { wait: true, role: 'manager', parentProfileId: 'etapa2-supervisor' };
}
function adaptiveManagerEffort(agentId, prompt) {
  const source = '/home/enok/.local/share/paseo-orchestrator';
  const script = "import sys,json;sys.path.insert(0,sys.argv[1]);from orchestrator.manager_effort import select;print(json.dumps(select(sys.argv[2],sys.argv[3],json.load(sys.stdin))))";
  try {
    return JSON.parse(execFileSync('python3', ['-c',script,source,flowDb(),String(agentId)], {input:JSON.stringify(typeof prompt === 'string' ? prompt : prompt?.prompt || ''),encoding:'utf8',timeout:3000,stdio:['pipe','pipe','pipe']}));
  } catch (error) {
    audit('manager_effort_selection_error', {agentId, error:String(error).slice(0,300)});
    return {effort:'high',reason:'state_unavailable_conservative'};
  }
}
function managerCandidate(config) {
  const role = config.labels?.['flow.role'] || config.env?.PASEO_FLOW_ROLE || config.role;
  if ([config.labels?.['flow.role'], config.env?.PASEO_FLOW_ROLE, config.role].some(value => ['programmer','reviewer'].includes(value)) || config.internal || config.discovery || config.metadataOnly || config.purpose) return false;
  const profile = config.profileId || config.agentProfileId;
  return isManagerRoot(config.cwd) &&
    (profile === 'etapa2-supervisor' || (!profile && config.provider === 'codex' && config.model === 'gpt-6.1-sol' && ['medium','high'].includes(config.thinkingOptionId)));
}
function nativeManager(config, agentId) {
  const staged = fileURLToPath(new URL('../orchestrator', import.meta.url));
  const source = existsSync(resolve(staged, 'orchestrator/policy_integration.py')) ? staged : resolve(staged, '../paseo-orchestrator');
  const script = `import sys,json,os
sys.path.insert(0,sys.argv[1])
sys.path.insert(1,str(__import__('pathlib').Path(sys.argv[1]).parents[2]))
from orchestrator import model_limits,core
if os.environ.get('PASEO_MODEL_LIMITS'): model_limits.LIMITS_FILE=__import__('pathlib').Path(os.environ['PASEO_MODEL_LIMITS'])
from orchestrator.policy_integration import native_prepare_manager
r=json.load(sys.stdin)
print(json.dumps(native_prepare_manager(r['config'],r.get('agentId'),r['config'].get('env'),r['config'].get('purpose'))))`;
  const out = execFileSync('python3', ['-c', script, source], {
    input: JSON.stringify({ config, agentId }), encoding: 'utf8', timeout: 20000, stdio: ['pipe','pipe','pipe'],
  });
  return JSON.parse(out);
}
export function resolveNewChat(config = {}) {
  if (!managerCandidate(config) || config.admissionTicket) return config;
  const ticket = verifiedAdmission(config.policyAgentId || config.agentId || config.env?.PASEO_AGENT_ID);
  if (ticket) {
    if (ticket.role !== 'manager') return config;
    // Retried create uses its already admitted UUID/model; it does not spawn a new owner.
    return { ...config, provider: ticket.provider, model: ticket.model, thinkingOptionId: ticket.effort,
      modeId: ticket.provider === 'claude' ? 'bypassPermissions' : 'full-access' };
  }
  return nativeManager(config, config.agentId);
}
export function assertCapacity(manager, agentId, policy = readPolicy(), reservations) {
  const busy = busyIds(manager, agentId, reservations);
  const limit = executorLimit(policy);
  if (busy.size >= limit)
    throw new Error(`Limite de ${limit} executores atingido; tarefa aguardará na fila.`);
}
export function readMemoryAvailableMiB() {
  const match = /^MemAvailable:\s+(\d+)\s+kB$/m.exec(readFileSync('/proc/meminfo', 'utf8'));
  if (!match) throw new Error('MemAvailable indisponível; novas execuções suspensas.');
  return Number(match[1]) / 1024;
}
function assertMode(provider, mode, config={}) {
  const allowed = ['codex','codex-programmer'].includes(provider) ? ['auto', 'read-only', ...(unrestrictedTools(config) ? ['full-access'] : [])] : provider === 'claude' ? ['default', 'acceptEdits', 'plan', ...((unrestrictedTools(config) || workerTools(config)) ? ['bypassPermissions'] : [])] : ['antigravity','antigravity2','antigravity3'].includes(provider) ? ['full-access'] : provider === 'grok' ? ['default','acceptEdits','bypassPermissions','plan'] : ['build', 'plan'];
  if (!allowed.includes(mode)) throw new Error('Modo bypass bloqueado pela política de autonomia em desenvolvimento.');
}

export function installManagerPolicy(AgentManager, dependencies = {}) {
  if (AgentManager.prototype[INSTALLED]) return;
  readPolicy();
  const memoryAvailable = dependencies.memoryAvailable ?? readMemoryAvailableMiB;
  const delay = dependencies.delay ?? (ms => new Promise(resolve => setTimeout(resolve, ms)));
  const queues = new WeakMap();
  const stateFor = manager => {
    if (!queues.has(manager)) queues.set(manager, { queue: new Map(), reservations: new Set() });
    return queues.get(manager);
  };
  const prototype = AgentManager.prototype;
  const register = prototype.registerSession;
  prototype.registerSession = function(session, ...args) {
    installSessionPolicy(session, args[0], args[1], this);
    return register.call(this, session, ...args);
  };
  const prepare = prototype.prepareSessionConfig;
  prototype.prepareSessionConfig = function(config, agentId, options = {}) {
    // The real SDK passes identity and environment separately from config.
    const purpose = options.purpose;
    // Rehydrating a stored session also serves transcript reads. Validate fresh
    // admission in startTurn; a stale decision must not hide existing history.
    if (purpose === "interactive") return prepare.call(this, applyCurrentPolicy({ ...config }), agentId, options);
    if (config.internal || config.discovery || config.metadataOnly || purpose && purpose !== 'interactive')
      return prepare.call(this, config, agentId, options);
    let normalized = { ...config, agentId, env: options.env || config.env, purpose };
    normalized = resolveNewChat(normalized);
    const claimedRole = normalized.env?.PASEO_FLOW_ROLE || normalized.labels?.['flow.role'];
    const claimedTicket = verifiedAdmission(agentId);
    if (['programmer','reviewer'].includes(claimedRole) && claimedTicket && claimedTicket.role !== claimedRole)
      throw new Error('Trabalhador sem ticket do controlador para este papel.');
    const protectedConfig = protectConfig(applyCurrentPolicy(normalized));
    const nextOptions = { ...options, env: normalized.env || options.env };
    if (options.env && normalized.env) Object.assign(options.env, normalized.env);
    for (const key of ['agentId','env','purpose','admissionTicket','idempotencyKey','labels','role','policyAction']) delete protectedConfig[key];
    return prepare.call(this, protectedConfig, agentId, nextOptions);
  };
  const stream = prototype.streamAgent;
  prototype.streamAgent = function(agentId, ...args) {
    const manager = this;
    const state = stateFor(manager);
    if (state.queue.has(agentId)) throw new Error('O agente já tem uma tarefa aguardando na fila.');
    if (manager.runs.hasRun(agentId)) return stream.call(manager, agentId, ...args);
    const ticket = { cancelled: false, since: Date.now() };
    state.queue.set(agentId, ticket);
    return (async function*() {
      let nativeStream;
      let waitingLogged = false;
      try {
        while (true) {
          if (ticket.cancelled) throw new Error('Tarefa em fila cancelada.');
          manager.requireSessionAgent(agentId);
          const policy = readPolicy();
          const first = state.queue.keys().next().value === agentId;
          const hasSlot = busyIds(manager, agentId, state.reservations).size < executorLimit(policy);
          const requiredMemory = policy.min_available_memory_mib ?? 1536;
          const memoryOkay = memoryAvailable() >= requiredMemory;
          if (first && hasSlot && memoryOkay) {
            // No await between admission and the native synchronous reservation.
            state.reservations.add(agentId);
            state.queue.delete(agentId);
            nativeStream = stream.call(manager, agentId, ...args);
            audit('turn_admitted', { agentId, requiredMemoryMiB: requiredMemory });
            break;
          }
          if (!waitingLogged) {
            audit('turn_queued', { agentId, reason: !hasSlot ? 'capacity' : !memoryOkay ? 'memory' : 'fifo' });
            waitingLogged = true;
          }
          if (Date.now() - ticket.since > (policy.queue_timeout_seconds ?? 3600) * 1000)
            throw new Error('Prazo de espera na fila excedido; tarefa preservada no histórico para retomada.');
          await delay(dependencies.pollMs ?? 500);
        }
        yield* nativeStream;
      } finally {
        state.queue.delete(agentId);
        state.reservations.delete(agentId);
      }
    })();
  };
  const cancel = prototype.cancelAgentRunNow;
  if (cancel) prototype.cancelAgentRunNow = function(agentId, ...args) {
    const ticket = stateFor(this).queue.get(agentId);
    if (ticket) {
      ticket.cancelled = true;
      audit('queued_turn_cancelled', { agentId });
      return Promise.resolve({ status: 'canceled' });
    }
    return cancel.call(this, agentId, ...args);
  };
  const mode = prototype.setAgentMode;
  prototype.setAgentMode = function(agentId, modeId) {
    assertMode(this.requireAgent(agentId).provider, modeId, {...this.requireAgent(agentId).config, policyAgentId:agentId});
    return mode.call(this, agentId, modeId);
  };
  const setModel = prototype.setAgentModel;
  prototype.setAgentModel = function(agentId, modelId) {
    const agent = this.requireAgent(agentId);
    const mark = assertTurnAdmission(agentId, agent.provider, modelId, null);
    if (mark === 'astra') return setModel.call(this, agentId, modelId);
    const resolved = assertModelAllowed(agent.provider, modelId);
    if (mark === 'admitted' && resolved !== modelId && modelId) throw new Error('Modelo admitido diverge do catálogo permitido.');
    return setModel.call(this, agentId, resolved);
  };
  const setThinking = prototype.setAgentThinkingOption;
  prototype.setAgentThinkingOption = function(agentId, thinkingId) {
    const provider = this.requireAgent(agentId).provider;
    const mark = assertTurnAdmission(agentId, provider, null, thinkingId);
    if (mark === 'admitted' && provider === 'grok') {
      assertThinkingAllowed(thinkingId);
      return setThinking.call(this, agentId, thinkingId);
    }
    if (mark === 'astra') {
      if (thinkingId !== 'medium') throw new Error('Astra somente esforço medium.');
      return setThinking.call(this, agentId, thinkingId);
    }
    assertProviderThinking(provider, thinkingId);
    return setThinking.call(this, agentId, thinkingId ?? defaultThinking(provider));
  };
  const feature = prototype.setAgentFeature;
  prototype.setAgentFeature = function(agentId, featureId, value) {
    if (!(unrestrictedTools({...this.requireAgent(agentId).config, policyAgentId:agentId}) || workerTools({...this.requireAgent(agentId).config, policyAgentId:agentId})) && featureId === 'auto_accept' && value) throw new Error('Aprovação automática irrestrita bloqueada.');
    if (['ultra','ultracode','xhigh'].includes(featureId) && value) throw new Error('Esforço acima de Alto proibido.');
    return feature.call(this, agentId, featureId, value);
  };
  const permission = prototype.respondToPermission;
  prototype.respondToPermission = function(agentId, requestId, response) {
    readPolicy();
    const onceActions = new Set(['allow_once', 'once', 'accept', 'allow', 'approve', 'implement', 'implement_resume']);
    if (!unrestrictedTools({...this.requireAgent(agentId).config, policyAgentId:agentId}) && response.behavior === 'allow' && (response.updatedPermissions?.length ||
      (response.selectedActionId && !onceActions.has(response.selectedActionId))))
      throw new Error('Operação protegida: use aprovação pontual, não autorização permanente.');
    audit('permission_response', { agentId, requestId, behavior: response.behavior });
    return permission.call(this, agentId, requestId, response);
  };
  prototype[INSTALLED] = true;
  audit('manager_policy_installed', { version: 2, pid: process.pid, limit: readPolicy().max_concurrent_executors });
}

export function installSessionPolicy(session, registeredConfig = {}, registeredAgentId, manager) {
  if (session[SESSION_GUARDED]) return;
  if (session.config) session.config.policyAgentId=registeredAgentId;
  registeredConfig.policyAgentId=registeredAgentId;
  if (session.setMode) {
    const mode = session.setMode.bind(session);
    session.setMode = modeId => { assertMode(session.provider, modeId, session.config || registeredConfig); return mode(modeId); };
  }
  if (session.setFeature) {
    const feature = session.setFeature.bind(session);
    session.setFeature = (featureId, value) => {
      if (!(unrestrictedTools(session.config || registeredConfig) || workerTools(session.config || registeredConfig)) && featureId === 'auto_accept' && value) throw new Error('Aprovação automática irrestrita bloqueada.');
      if (['ultra','ultracode','xhigh'].includes(featureId) && value) throw new Error('Esforço acima de Alto proibido.');
      return feature(featureId, value);
    };
  }
  const agentId = registeredAgentId || session.agentId || session.id || session.config?.agentId;
  if (session.setModel) {
    const setModel = session.setModel.bind(session);
    session.setModel = value => {
      const mark = assertTurnAdmission(agentId, session.provider, value, null);
      if (mark === 'astra') return setModel(value);
      return setModel(assertModelAllowed(session.provider, value));
    };
  }
  if (session.setThinkingOption) {
    const setThinking = session.setThinkingOption.bind(session);
    session.setThinkingOption = value => {
      const mark = assertTurnAdmission(agentId, session.provider, null, value);
      if (mark === 'admitted' && session.provider === 'grok') {
        assertThinkingAllowed(value);
        return setThinking(value);
      }
      if (mark === 'astra') {
        if (value !== 'medium') throw new Error('Astra somente esforço medium.');
        return setThinking(value);
      }
      assertProviderThinking(session.provider, value);
      return setThinking(value ?? defaultThinking(session.provider));
    };
  }
  if (session.startTurn) {
    const start = session.startTurn.bind(session);
    session.startTurn = async (...args) => {
      const runtime = await session.getRuntimeInfo?.();
      const model = runtime?.model ?? session.config?.model ?? registeredConfig.model;
      let effort = runtime?.thinkingOptionId ?? session.config?.thinkingOptionId ?? registeredConfig.thinkingOptionId;
      const admission = verifiedAdmission(agentId);
      if (admission?.role === 'manager' && session.provider === 'codex' && model === 'gpt-6.1-sol' && readModelLimits().supervision?.adaptive_effort?.enabled === true) {
        const choice = adaptiveManagerEffort(agentId, args[0]);
        await session.setThinkingOption(choice.effort);
        effort = choice.effort;
        if (manager) {
          const agent = manager.requireAgent(agentId);
          agent.config.thinkingOptionId = effort;
          if (agent.runtimeInfo) agent.runtimeInfo = {...agent.runtimeInfo, thinkingOptionId:effort};
          manager.touchUpdatedAt(agent);
          manager.emitState(agent);
        }
        audit('manager_effort_selected', {agentId, ...choice});
      }
      const mark = assertTurnAdmission(agentId, session.provider, model, effort);
      const turnConfig = { ...registeredConfig, ...(session.config || {}), role: verifiedAdmission(agentId)?.role, provider: session.provider, model, thinkingOptionId: effort, agentId };
      if (!agentId || typeof turnConfig.cwd !== "string" || !turnConfig.cwd) throw new Error("Contexto do agente indisponível: ID e diretório são obrigatórios.");
      guardUnticketed(turnConfig, mark);
      assertCurrentOwner(agentId, turnConfig);
      applyCurrentPolicy(session.config || registeredConfig);
      if (args[0] && typeof args[0] === 'object') applyCurrentPolicy(args[0]);
      if (mark !== 'astra' && !(mark === 'admitted' && session.provider === 'grok')) assertModelAllowed(session.provider, model);
      if (mark === 'admitted' && session.provider === 'grok') assertThinkingAllowed(effort);
      else if (mark !== 'astra') assertProviderThinking(session.provider, effort);
      return start(...args);
    };
  }
  session[SESSION_GUARDED] = true;
}
function decision(permissionDecision, reason) {
  return { hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision, permissionDecisionReason: reason } };
}
function branchIsDevelopment(cwd) {
  try {
    const branch = execFileSync('git', ['-C', cwd, 'symbolic-ref', '--short', 'HEAD'], { encoding: 'utf8', timeout: 2000 }).trim();
    return !['main', 'master', 'production', 'prod'].includes(branch);
  } catch { return false; }
}
export function classifyCommand(command, cwd) {
  if (unrestrictedTools()) return typeof command === 'string' && command.trim() ? 'allow' : 'deny';
  if (typeof command !== 'string' || !isDevelopmentPath(cwd)) return 'ask';
  if (unattendedDevelopment(cwd)) {
    try {
      return execFileSync('/home/enok/.local/share/paseo-orchestrator/bin/python3',['-c',
        'import sys;sys.path.insert(0,"/home/enok/.local/share/paseo-orchestrator");from orchestrator.autonomy import shell_decision;print(shell_decision(sys.stdin.read(),sys.argv[1]))',cwd],
        {input:command,encoding:'utf8',timeout:2000,stdio:['pipe','pipe','ignore']}).trim();
    } catch { return 'deny'; }
  }
  // Use the controller's shell parser before creating a permission request.
  // This also covers ordinary app-created chats without orchestration labels.
  try {
    const result = execFileSync('/home/enok/.local/share/paseo-orchestrator/bin/python3', ['-c',
      'import sys; sys.path.insert(0,"/home/enok/.local/share/paseo-orchestrator"); from orchestrator.permissions import safe_command; from orchestrator.core import autonomy_policy; print("allow" if autonomy_policy().get("auto_approve_development_plans") is True and safe_command(sys.stdin.read(),sys.argv[1]) else "ask")', cwd],
      { input: command, encoding: 'utf8', timeout: 2000, stdio: ['pipe', 'pipe', 'ignore'] });
    if (result.trim() === 'allow') return 'allow';
  } catch { /* Fall back to the native conservative classifier. */ }
  // Conservative command admission, not a shell parser or a security sandbox.
  // The process-level filesystem/network boundary is configured separately.
  if (/[;&|`\n\r<>]|\$\(|\$\{|\\/.test(command)) return 'ask';
  if (/(?:^|\s)(?:rm|rmdir|unlink|shred|dd|mkfs|sudo|su|docker|podman|systemctl|service|ssh|scp|curl|wget|kubectl|helm|terraform)(?:\s|$)/i.test(command)) return 'ask';
  if (/\b(?:deploy|publish|billing|payment|truncate|drop\s+(?:database|table)|git\s+push|git\s+reset|git\s+clean)\b/i.test(command)) return 'ask';
  for (const token of command.split(/\s+/)) {
    const path = token.replace(/^['"]|['"]$/g, '');
    if ((path.startsWith('/') || path.startsWith('../')) && !isDevelopmentPath(path, cwd)) return 'ask';
  }
  if (/^paseo-flow\s+(?:submit|approve|status|models|report|projects|prepare-project|pause)\b/.test(command)) return 'allow';
  if (/^git\s+(?:add|commit|merge|cherry-pick)\b/.test(command)) return branchIsDevelopment(cwd) ? 'allow' : 'ask';
  if (/^(?:pwd|ls(?:\s|$)|rg\s|cat\s|head\s|tail\s|wc\s|git\s+(?:status|diff|log|show|rev-parse)\b)/.test(command)) return 'allow';
  if (/^(?:python3?\s+-m\s+(?:pytest|unittest|compileall)\b|pytest\b|node\s+--test\b|npm\s+(?:test\b|run\s+(?:test|lint|build|typecheck|check)\b)|pnpm\s+(?:test|lint|build|typecheck)\b)/.test(command)) return 'allow';
  return 'ask';
}
export async function approvalHook(input, sessionConfig = {}) {
  readPolicy();
  if (unrestrictedTools(sessionConfig) && !sessionConfig.internal) return decision('allow','Autorização explícita do usuário para ferramentas sem bloqueios; política de modelos preservada.');
  const cwd = input.cwd ?? sessionConfig.cwd;
  if (workerTools(sessionConfig)) {
    if (isDevelopmentPath(cwd) && canonical(cwd)===canonical(sessionConfig.cwd)) return decision('allow','Trabalhador autorizado dentro da worktree isolada; proteção de host/rede aplicada pelo runtime.');
    return decision('deny','Trabalhador fora da worktree admitida. Encaminhe a necessidade administrativa ao gerente.');
  }
  const tool = input.tool_name;
  const toolInput = input.tool_input ?? {};
  if (!sessionConfig.internal && unattendedDevelopment(cwd)) {
    if (['AskUserQuestion','EnterPlanMode','ExitPlanMode'].includes(tool))
      return decision('deny','O usuário autorizou execução sem acompanhamento. Assuma padrões razoáveis, execute o plano e registre decisões; não abra confirmação.');
    if (EDIT_TOOLS.has(tool)) {
      const path=toolInput.file_path ?? toolInput.path ?? toolInput.notebook_path;
      return decision(isDevelopmentPath(path,cwd)?'allow':'deny','Edição autônoma limitada ao desenvolvimento isolado.');
    }
    if (tool==='Bash')return decision(classifyCommand(toolInput.command,cwd),'Autorização permanente de desenvolvimento. Ações fora do escopo são bloqueadas; continue com alternativa ou reporte o impedimento.');
    return decision('allow','Ferramentas autorizadas para execução sem acompanhamento dentro do desenvolvimento isolado.');
  }
  if (READ_TOOLS.has(tool)) return {};
  if (tool === 'Skill' && ['paseo','paseo-handoff','paseo-committee','paseo-advisor','paseo-help'].includes(toolInput.skill))
    return decision('allow', 'Skill oficial de desenvolvimento autorizada.');
  if (EDIT_TOOLS.has(tool)) {
    const path = toolInput.file_path ?? toolInput.path ?? toolInput.notebook_path;
    return !sessionConfig.internal && isDevelopmentPath(path, cwd)
      ? decision('allow', 'Edição autorizada dentro do ambiente de desenvolvimento.')
      : decision('ask', 'Gravação fora das raízes de desenvolvimento ou por agente interno.');
  }
  if (tool === 'Bash') return decision(classifyCommand(toolInput.command, cwd),
    'Política de desenvolvimento: comandos rotineiros permitidos; efeitos destrutivos, produção, rede externa ou custo exigem revisão.');
  if (tool?.startsWith('mcp__paseo__') && SAFE_PASEO.has(tool.slice('mcp__paseo__'.length)))
    return decision('allow', 'Delegação gerenciada pelo Paseo, sujeita à fila, limites e raízes aprovadas.');
  return decision('ask', 'Ferramenta não coberta pela autorização de desenvolvimento.');
}
export function installClaudePolicy(ClaudeAgentSession) {
  if (ClaudeAgentSession.prototype[INSTALLED]) return;
  const build = ClaudeAgentSession.prototype.buildOptions;
  ClaudeAgentSession.prototype.buildOptions = async function(...args) {
    const options = await build.apply(this, args);
    applyCurrentPolicy(options);
    if ((unrestrictedTools(this.config) || workerTools(this.config)) && !this.config?.internal) {
      options.permissionMode = 'bypassPermissions';
      options.allowDangerouslySkipPermissions = true;
    }
    if (!['default', 'acceptEdits', 'plan', ...((unrestrictedTools(this.config) || workerTools(this.config)) ? ['bypassPermissions'] : [])].includes(options.permissionMode)) throw new Error('Modo Claude bypass bloqueado.');
    if (!(unrestrictedTools(this.config) || workerTools(this.config))) options.allowDangerouslySkipPermissions = false;
    const hook = input => approvalHook(input, this.config ?? {});
    options.hooks = { ...options.hooks, PreToolUse: [...(options.hooks?.PreToolUse ?? []), { hooks: [hook] }] };
    return options;
  };
  ClaudeAgentSession.prototype[INSTALLED] = true;
}


// Codex 0.164 TurnStartParams does not support developerInstructions/config.
// Updating those discarded fields changes UI metadata, not model-visible history.
// Inject the current operator policy through the supported history RPC before
// each session's first turn, and again whenever the policy changes.
export function installCodexHistoryPolicy(CodexSession) {
  const key = Symbol.for('paseo.codex.historyPolicy.v1');
  const proto = CodexSession.prototype;
  if (proto[key]) return;
  const build = proto.buildTurnStartParams;
  if (typeof build !== 'function') throw new Error('Codex turn builder incompatible with policy injection');
  proto.buildTurnStartParams = async function (...args) {
    const policy = currentPolicyText();
    const text = '<paseo_runtime_policy version="3">\n' +
      'Atualização administrativa das instruções de execução desta sessão. ' +
      'Esta política substitui integralmente as regras históricas de modelos, esforços, contas e substituição, ' +
      'inclusive a antiga exigência de programação exclusivamente Grok sem fallback. ' +
      'A gerência deve delegar pelo controlador usando a cadeia abaixo. ' +
      'O histórico das entregas e as demais instruções de projeto permanecem válidos.\n' +
      policy + '\n</paseo_runtime_policy>';
    const fingerprint = this.currentThreadId + '\n' + text;
    if (this._paseoInjectedPolicy !== fingerprint) {
      if (!this.client || !this.currentThreadId) throw new Error('Codex thread must be loaded before policy injection');
      await this.client.request('thread/inject_items', {
        threadId: this.currentThreadId,
        items: [{type: 'message', role: 'developer', content: [{type: 'input_text', text}]}],
      });
      this._paseoInjectedPolicy = fingerprint;
    }
    return build.apply(this, args);
  };
  Object.defineProperty(proto, key, {value: true});
}
