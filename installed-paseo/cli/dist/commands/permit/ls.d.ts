import type { Command } from "commander";
import type { AgentSnapshotPayload } from "@getpaseo/protocol/messages";
import type { CommandOptions, ListResult, OutputSchema } from "../../output/index.js";
/** Permission list item for display */
export interface PermissionListItem {
    id: string;
    agentId: string;
    agentShortId: string;
    name: string;
    description: string;
}
/** Schema for permit ls output */
export declare const permitLsSchema: OutputSchema<PermissionListItem>;
export type PermitLsResult = ListResult<PermissionListItem>;
/** Collect the pending permissions of every agent */
export declare function listPendingPermissions(agents: AgentSnapshotPayload[]): PermitLsResult;
export interface PermitLsOptions extends CommandOptions {
    host?: string;
}
export declare function runLsCommand(options: PermitLsOptions, _command: Command): Promise<PermitLsResult>;
//# sourceMappingURL=ls.d.ts.map