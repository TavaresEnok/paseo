import { Command } from "commander";
import type { CommandOptions, SingleResult, OutputSchema } from "../../output/index.js";
/** Result type for agent archive command */
export interface AgentArchiveResult {
    agentId: string;
    status: "archived";
    archivedAt: string;
}
/** Schema for archive command output */
export declare const archiveSchema: OutputSchema<AgentArchiveResult>;
export declare function addArchiveOptions(cmd: Command): Command;
export interface AgentArchiveOptions extends CommandOptions {
    force?: boolean;
    host?: string;
}
export type AgentArchiveCommandResult = SingleResult<AgentArchiveResult>;
export declare function runArchiveCommand(agentIdArg: string, options: AgentArchiveOptions, _command: Command): Promise<AgentArchiveCommandResult>;
//# sourceMappingURL=archive.d.ts.map