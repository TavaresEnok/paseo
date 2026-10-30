import type { Command } from "commander";
import type { SingleResult } from "../../output/index.js";
interface WorkspaceRenameResult {
    workspaceId: string;
    /** Raw title override; null once it has been reset to the derived name. */
    title: string | null;
}
export interface WorkspaceRenameOptions {
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
    reset?: boolean;
}
/**
 * Resolve the title to send to the daemon. Null clears the override and
 * reverts the workspace to its branch- or directory-derived name.
 */
export declare function resolveWorkspaceTitle(input: {
    title?: string;
    reset?: boolean;
}): string | null;
export declare function runRenameCommand(workspaceId: string, titleArg: string | undefined, options: WorkspaceRenameOptions, _command: Command): Promise<SingleResult<WorkspaceRenameResult>>;
export {};
//# sourceMappingURL=rename.d.ts.map