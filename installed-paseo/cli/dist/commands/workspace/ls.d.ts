import type { Command } from "commander";
import type { ListResult } from "../../output/index.js";
import { type WorkspaceRow } from "./shared.js";
export interface WorkspaceLsOptions {
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
    /** --background: Include background workspaces */
    background?: boolean;
}
export declare function runLsCommand(options: WorkspaceLsOptions, _command: Command): Promise<ListResult<WorkspaceRow>>;
//# sourceMappingURL=ls.d.ts.map