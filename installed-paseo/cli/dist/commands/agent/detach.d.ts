import type { Command } from "commander";
import type { CommandOptions, SingleResult } from "../../output/index.js";
interface AgentDetachResult {
    agentId: string;
    status: "detached";
}
export declare function runDetachCommand(agentIdArg: string, options: CommandOptions, _command: Command): Promise<SingleResult<AgentDetachResult>>;
export {};
//# sourceMappingURL=detach.d.ts.map