import type { Command } from "commander";
import type { CommandOptions, SingleResult } from "../../output/index.js";
import { type WorkspaceRow } from "./shared.js";
export interface WorkspaceCreateOptions extends CommandOptions {
    isolation?: string;
    path?: string;
    project?: string;
    title?: string;
    mode?: string;
    worktreeSlug?: string;
    newBranch?: string;
    base?: string;
    branch?: string;
    prNumber?: string;
    forge?: string;
    background?: boolean;
}
export declare function buildWorkspaceSource(options: WorkspaceCreateOptions): {
    projectId?: string | undefined;
    kind: "directory";
    path: string;
} | {
    baseBranch?: string | undefined;
    branchName?: string | undefined;
    action: "branch-off";
    kind: "worktree";
    cwd?: string;
    projectId?: string;
    worktreeSlug?: string;
} | {
    action: "checkout";
    refName: string;
    kind: "worktree";
    cwd?: string;
    projectId?: string;
    worktreeSlug?: string;
} | {
    action: "checkout";
    checkoutSource: {
        number: number;
        forge?: string | undefined;
        kind: "change_request";
    };
    kind: "worktree";
    cwd?: string;
    projectId?: string;
    worktreeSlug?: string;
};
export declare function runCreateCommand(options: WorkspaceCreateOptions, _command: Command): Promise<SingleResult<WorkspaceRow>>;
//# sourceMappingURL=create.d.ts.map