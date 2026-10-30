import { Command } from "commander";
import type { CommandOptions, SingleResult, OutputSchema } from "../../output/index.js";
export interface AgentReloadResult {
    agentId: string;
    status: "reloaded";
    timelineSize: number;
}
export declare const reloadSchema: OutputSchema<AgentReloadResult>;
export declare function addReloadOptions(cmd: Command): Command;
export interface AgentReloadOptions extends CommandOptions {
    host?: string;
}
export type AgentReloadCommandResult = SingleResult<AgentReloadResult>;
export declare function runReloadCommand(agentIdArg: string, options: AgentReloadOptions, _command: Command): Promise<AgentReloadCommandResult>;
//# sourceMappingURL=reload.d.ts.map