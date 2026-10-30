import type { Command } from "commander";
import type { OutputSchema, SingleResult } from "../output/index.js";
import type { CommandOptions } from "../output/with-output.js";
type CloneProtocol = "https" | "ssh";
interface CloneCommandOptions extends CommandOptions {
    protocol?: CloneProtocol;
}
export interface CloneResult {
    repo: string;
    checkoutPath: string;
    projectId: string;
    projectName: string;
}
export declare const cloneSchema: OutputSchema<CloneResult>;
export declare function runCloneCommand(repo: string, options: CloneCommandOptions, _command: Command): Promise<SingleResult<CloneResult>>;
export {};
//# sourceMappingURL=clone.d.ts.map