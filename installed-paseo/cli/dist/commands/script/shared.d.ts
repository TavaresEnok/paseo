import type { DaemonTarget } from "../../utils/daemon-target.js";
import type { DaemonClient } from "@getpaseo/client/internal/daemon-client";
import type { CommandError, CommandOptions } from "../../output/index.js";
export interface WorkspaceScriptCommandOptions extends CommandOptions {
    host?: string;
    cwd?: string;
    workspace?: string;
}
export declare function connectWorkspaceScriptClient(target: DaemonTarget): Promise<DaemonClient>;
export declare function resolveWorkspaceScriptWorkspaceId(client: DaemonClient, options: WorkspaceScriptCommandOptions): Promise<string>;
export declare function toWorkspaceScriptCommandError(code: string, action: string, error: unknown): CommandError;
//# sourceMappingURL=shared.d.ts.map