import type { Command } from "commander";
import type { SingleResult } from "../../output/index.js";
interface WorkspaceSetupResult {
    workspaceId: string;
    status: "started" | "already_allowed";
}
export declare function runSetupCommand(workspaceId: string, options: {
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
}, _command: Command): Promise<SingleResult<WorkspaceSetupResult>>;
export {};
//# sourceMappingURL=setup.d.ts.map