import type { Command } from "commander";
import type { AgentPermissionRequest, AgentPermissionResponse } from "@getpaseo/protocol/agent-types";
import { connectToDaemon } from "../../utils/client.js";
import type { CommandOptions, ListResult, OutputSchema } from "../../output/index.js";
/** Permission response item for display */
export interface PermissionResponseItem {
    requestId: string;
    agentId: string;
    agentShortId: string;
    name: string;
    result: string;
}
/** Schema for permit allow/deny output */
export declare const permitResponseSchema: OutputSchema<PermissionResponseItem>;
/** Transform a permission the agent answered to a response item */
export declare function toPermissionResponseItem(agentId: string, permission: AgentPermissionRequest, result: "allowed" | "denied"): PermissionResponseItem;
export type PermitAllowResult = ListResult<PermissionResponseItem>;
export interface PermitAllowOptions extends CommandOptions {
    all?: boolean;
    input?: string;
    host?: string;
}
export interface PermitClient {
    fetchAgent(options: {
        agentId: string;
    }): Promise<{
        agent: {
            id: string;
            pendingPermissions?: AgentPermissionRequest[];
        };
    } | null>;
    respondToPermissionAndWait(agentId: string, requestId: string, response: AgentPermissionResponse): Promise<unknown>;
    close(): Promise<void>;
}
export type PermitClientConnector = (options: Parameters<typeof connectToDaemon>[0]) => Promise<PermitClient>;
export declare function createAllowCommand(connect?: PermitClientConnector): (agentIdOrPrefix: string, reqId: string | undefined, options: PermitAllowOptions, _command: Command) => Promise<PermitAllowResult>;
export declare const runAllowCommand: (agentIdOrPrefix: string, reqId: string | undefined, options: PermitAllowOptions, _command: Command) => Promise<PermitAllowResult>;
//# sourceMappingURL=allow.d.ts.map