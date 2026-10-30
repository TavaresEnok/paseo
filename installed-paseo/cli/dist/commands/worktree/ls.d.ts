import type { Command } from "commander";
import type { CommandOptions, ListResult, OutputSchema } from "../../output/index.js";
/** Worktree list item for display */
export interface WorktreeListItem {
    name: string;
    branch: string;
    cwd: string;
    agent: string;
}
/** Schema for worktree ls output */
export declare const worktreeLsSchema: OutputSchema<WorktreeListItem>;
export type WorktreeLsResult = ListResult<WorktreeListItem>;
export interface WorktreeLsOptions extends CommandOptions {
    host?: string;
    cwd?: string;
}
export declare function runLsCommand(options: WorktreeLsOptions, _command: Command): Promise<WorktreeLsResult>;
//# sourceMappingURL=ls.d.ts.map