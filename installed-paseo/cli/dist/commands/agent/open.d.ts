import type { Command } from "commander";
import type { CommandOptions, SingleResult } from "../../output/index.js";
interface OpenAgentResult {
    agentId: string;
    serverId: string;
    status: "opened";
}
export declare function addOpenOptions(command: Command): Command;
export declare function runOpenCommand(agentIdArg: string, options: CommandOptions, _command: Command): Promise<SingleResult<OpenAgentResult>>;
export {};
//# sourceMappingURL=open.d.ts.map