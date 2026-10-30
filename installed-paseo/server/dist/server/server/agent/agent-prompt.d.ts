import { type AgentPromptSource } from "./agent-messages/index.js";
import type { Logger } from "pino";
import type { AgentPromptInput, AgentRunOptions } from "./agent-sdk-types.js";
import type { AgentManager, ManagedAgent } from "./agent-manager.js";
import type { AgentStorage } from "./agent-storage.js";
import type { ActiveTurnBehavior } from "@getpaseo/protocol/messages";
export type AgentUnarchiveController = Pick<AgentManager, "notifyAgentState" | "unarchiveSnapshot">;
export type AgentRunController = Pick<AgentManager, "getAgent" | "tryRunOutOfBand" | "hasInFlightRun" | "replaceAgentRun" | "steerOrReplaceActiveTurn" | "streamAgent"> & {
    reloadAgentSession(agentId: string): Promise<unknown>;
};
export interface StartAgentRunOptions {
    /** Called after selecting the run, before consuming its events. */
    onDispatch?: (disposition: PromptDispatchDisposition) => void;
    replaceRunning?: boolean;
    activeTurnBehavior?: ActiveTurnBehavior;
    runOptions?: AgentRunOptions;
    /** Ask the provider to deny permissions blocking this steer. */
    clearPendingPermissions?: boolean;
}
export type PromptDispatchDisposition = "out_of_band" | "steered" | "turn_started";
export declare function startAgentRun(agentManager: AgentRunController, agentId: string, prompt: AgentPromptInput, logger: Logger, options?: StartAgentRunOptions): Promise<{
    disposition: PromptDispatchDisposition;
}>;
/**
 * Clear the archived flag from a stored agent record.
 * Shared across Session (app/WS), MCP, and CLI so every surface that acts on
 * an archived agent unarchives it the same way.
 */
export declare function unarchiveAgentState(_agentStorage: AgentStorage, agentManager: AgentUnarchiveController, agentId: string, updates?: {
    workspaceId?: string;
    labels?: Record<string, string | null>;
}): Promise<boolean>;
export interface SendPromptToAgentParams {
    onDispatch?: StartAgentRunOptions["onDispatch"];
    agentManager: AgentManager;
    agentStorage: AgentStorage;
    agentId: string;
    /** Prompt to dispatch to the provider (may include image blocks or wrapped text). */
    prompt: AgentPromptInput;
    source?: AgentPromptSource;
    messageId?: string;
    activeTurnBehavior?: ActiveTurnBehavior;
    runOptions?: AgentRunOptions;
    /** Optional mode to set on the agent before the run starts. */
    sessionMode?: string;
    /**
     * Default true. When false, archived agents are skipped instead of being
     * unarchived. Use false for system-injected prompts (chat mentions,
     * schedule fires, notify-on-finish).
     */
    unarchive?: boolean;
    /** See {@link StartAgentRunOptions.clearPendingPermissions}. */
    clearPendingPermissions?: boolean;
    logger: Logger;
}
export interface StartCreatedAgentInitialPromptParams {
    agentStorage: AgentStorage;
    agentManager: AgentManager;
    agentId: string;
    snapshot?: ManagedAgent;
    prompt: AgentPromptInput | null;
    source?: AgentPromptSource;
    runOptions?: AgentRunOptions;
    logger: Logger;
}
export declare function waitForAgentRunStartWithTimeout(agentManager: AgentManager, agentId: string, signal?: AbortSignal): Promise<void>;
/**
 * Full send-prompt orchestration: (optional unarchive) → load → (optional
 * mode change) → start run.
 *
 * Every surface that sends a prompt to an agent (Session/WS, MCP, CLI-through-MCP,
 * chat mentions, notify-on-finish) MUST go through this so behavior can never
 * drift between them.
 *
 * When `unarchive` is false and the agent is archived, the call is a silent
 * no-op (returns the normal turn-start disposition) — the agent is not run.
 */
export declare function sendPromptToAgent(params: SendPromptToAgentParams): Promise<{
    disposition: PromptDispatchDisposition;
}>;
/** Dispatch daemon-prepared context without reclassifying it as human input. */
export declare function sendPreparedPromptToAgent(params: Omit<SendPromptToAgentParams, "source" | "messageId">): Promise<{
    disposition: PromptDispatchDisposition;
}>;
export declare function startCreatedAgentInitialPrompt(params: StartCreatedAgentInitialPromptParams): Promise<ManagedAgent>;
//# sourceMappingURL=agent-prompt.d.ts.map