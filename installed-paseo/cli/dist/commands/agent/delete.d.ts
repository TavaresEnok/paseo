import type { Command } from "commander";
export declare function addDeleteOptions(cmd: Command): Command;
import type { CommandOptions, SingleResult, OutputSchema } from "../../output/index.js";
export interface DeleteResult {
    deletedCount: number;
    agentIds: string[];
}
export declare const deleteSchema: OutputSchema<DeleteResult>;
export interface AgentDeleteOptions extends CommandOptions {
    all?: boolean;
    cwd?: string;
}
export type AgentDeleteResult = SingleResult<DeleteResult>;
export declare function runDeleteCommand(id: string | undefined, options: AgentDeleteOptions, _command: Command): Promise<AgentDeleteResult>;
//# sourceMappingURL=delete.d.ts.map