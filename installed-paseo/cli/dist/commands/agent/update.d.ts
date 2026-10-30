import type { Command } from "commander";
import type { AgentProviderNotice } from "@getpaseo/protocol/agent-types";
import type { AgentSnapshotPayload } from "@getpaseo/protocol/messages";
import type { CommandOptions, SingleResult, OutputSchema } from "../../output/index.js";
/** Result type for agent update command */
export interface AgentUpdateResult {
    agentId: string;
    name: string | null;
    labels: string;
    thinkingOptionId: string | null;
    noticeType: AgentProviderNotice["type"] | null;
    notice: string | null;
}
/** Schema for update command output */
export declare const updateSchema: OutputSchema<AgentUpdateResult>;
export interface AgentUpdateOptions extends CommandOptions {
    name?: string;
    label?: string[];
    thinking?: string;
    host?: string;
}
export type AgentUpdateCommandResult = SingleResult<AgentUpdateResult>;
export interface AgentMetadataChanges {
    name?: string;
    labels?: Record<string, string>;
}
interface AgentUpdateServerInfo {
    features?: {
        agentThinkingUpdate?: boolean;
    };
}
export interface AgentUpdateClient {
    getLastServerInfoMessage(): AgentUpdateServerInfo | null;
    updateAgent(agentId: string, updates: AgentMetadataChanges): Promise<void>;
    setAgentThinkingOption(agentId: string, thinkingOptionId: string): Promise<AgentProviderNotice | null>;
}
export type AgentChanges = {
    type: "metadata";
    updates: AgentMetadataChanges;
} | {
    type: "thinking";
    thinkingOptionId: string;
};
export interface AppliedAgentChanges {
    notice: AgentProviderNotice | null;
}
export declare function toAgentUpdateResult(agent: Pick<AgentSnapshotPayload, "id" | "title" | "labels" | "effectiveThinkingOptionId">, appliedChanges: AppliedAgentChanges): AgentUpdateResult;
export declare function applyAgentChanges(client: AgentUpdateClient, agentId: string, changes: AgentChanges): Promise<AppliedAgentChanges>;
export declare function runUpdateCommand(agentIdArg: string, options: AgentUpdateOptions, _command: Command): Promise<AgentUpdateCommandResult>;
export {};
//# sourceMappingURL=update.d.ts.map