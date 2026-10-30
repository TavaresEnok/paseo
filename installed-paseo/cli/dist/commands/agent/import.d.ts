import type { Command } from "commander";
import type { CommandOptions, SingleResult } from "../../output/index.js";
import { type AgentRunResult } from "./run.js";
export declare function addImportOptions(cmd: Command): Command;
export interface AgentImportOptions extends CommandOptions {
    provider?: string;
    cwd?: string;
    label?: string[];
    host?: string;
}
export type AgentImportCommandResult = SingleResult<AgentRunResult>;
export declare function resolveImportCwd(explicitCwd: string | undefined, defaultCwd: string): string;
export declare function runImportCommand(sessionIdArg: string, options: AgentImportOptions, _command: Command): Promise<AgentImportCommandResult>;
//# sourceMappingURL=import.d.ts.map