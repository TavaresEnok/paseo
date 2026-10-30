import type { Command } from "commander";
import type { OutputSchema, SingleResult } from "../../output/index.js";
import { type WorktreeCreateOptions } from "./create-input.js";
export interface WorktreeCreateResult {
    name: string;
    branchName: string;
    worktreePath: string;
}
export declare const createSchema: OutputSchema<WorktreeCreateResult>;
export declare function runCreateCommand(options: WorktreeCreateOptions, _command: Command): Promise<SingleResult<WorktreeCreateResult>>;
//# sourceMappingURL=create.d.ts.map