import type { Command } from "commander";
import type { CommandOptions, OutputSchema, AnyCommandResult } from "../../output/index.js";
import type { AgentMode } from "@getpaseo/protocol/agent-types";
/** Result for setting mode */
export interface SetModeResult {
    agentId: string;
    mode: string;
}
/** Schema for mode list output */
export declare const modeListSchema: OutputSchema<AgentMode>;
/** Schema for set mode output */
export declare const setModeSchema: OutputSchema<SetModeResult>;
export interface AgentModeOptions extends CommandOptions {
    list?: boolean;
}
export type AgentModeResult = AnyCommandResult<any>;
export declare function runModeCommand(id: string, mode: string | undefined, options: AgentModeOptions, _command: Command): Promise<AgentModeResult>;
//# sourceMappingURL=mode.d.ts.map