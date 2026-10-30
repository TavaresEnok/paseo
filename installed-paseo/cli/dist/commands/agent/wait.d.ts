import { Command } from "commander";
import type { CommandOptions, SingleResult, OutputSchema } from "../../output/index.js";
/** Result type for agent wait command */
export interface AgentWaitResult {
    agentId: string;
    status: "idle" | "timeout" | "permission" | "error";
    message: string;
}
/** Schema for agent wait output */
export declare const agentWaitSchema: OutputSchema<AgentWaitResult>;
export interface AgentWaitOptions extends CommandOptions {
    timeout?: string;
    host?: string;
}
export declare function addWaitOptions(cmd: Command): Command;
export declare function runWaitCommand(agentIdArg: string, options: AgentWaitOptions, _command: Command): Promise<SingleResult<AgentWaitResult>>;
//# sourceMappingURL=wait.d.ts.map