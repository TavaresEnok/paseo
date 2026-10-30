import { Command } from "commander";
import type { CommandOptions, SingleResult, OutputSchema } from "../../output/index.js";
/** Result type for agent stop command */
export interface StopResult {
    stoppedCount: number;
    agentIds: string[];
}
/** Schema for stop command output */
export declare const stopSchema: OutputSchema<StopResult>;
export declare function addStopOptions(cmd: Command): Command;
export interface AgentStopOptions extends CommandOptions {
    all?: boolean;
    cwd?: string;
}
export type AgentStopResult = SingleResult<StopResult>;
export declare function runStopCommand(id: string | undefined, options: AgentStopOptions, _command: Command): Promise<AgentStopResult>;
//# sourceMappingURL=stop.d.ts.map