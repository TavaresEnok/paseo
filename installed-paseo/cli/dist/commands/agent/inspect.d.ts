import type { Command } from "commander";
import type { CommandOptions, ListResult } from "../../output/index.js";
export declare function addInspectOptions(cmd: Command): Command;
/** Key-value row for table display */
interface InspectRow {
    key: string;
    value: string;
}
export type AgentInspectResult = ListResult<InspectRow>;
export interface AgentInspectOptions extends CommandOptions {
    host?: string;
}
export declare function runInspectCommand(agentIdArg: string, options: AgentInspectOptions, _command: Command): Promise<AgentInspectResult>;
export {};
//# sourceMappingURL=inspect.d.ts.map