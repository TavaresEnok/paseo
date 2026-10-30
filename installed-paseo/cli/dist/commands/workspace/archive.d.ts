import type { Command } from "commander";
import type { SingleResult } from "../../output/index.js";
interface WorkspaceArchiveResult {
    workspaceId: string;
    status: "archived";
    archivedAt: string;
}
export declare function runArchiveCommand(workspaceId: string, options: {
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
}, _command: Command): Promise<SingleResult<WorkspaceArchiveResult>>;
export {};
//# sourceMappingURL=archive.d.ts.map