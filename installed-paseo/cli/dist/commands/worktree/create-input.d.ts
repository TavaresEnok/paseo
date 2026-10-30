import type { DaemonClient } from "@getpaseo/client/internal/daemon-client";
import type { CommandOptions } from "../../output/index.js";
export interface WorktreeCreateOptions extends CommandOptions {
    host?: string;
    cwd?: string;
    mode?: string;
    newBranch?: string;
    base?: string;
    branch?: string;
    prNumber?: string;
}
type CreatePaseoWorktreeRequest = Parameters<DaemonClient["createPaseoWorktree"]>[0];
export declare function buildCreateWorktreeRequest(options: WorktreeCreateOptions, cwd: string): CreatePaseoWorktreeRequest;
export {};
//# sourceMappingURL=create-input.d.ts.map