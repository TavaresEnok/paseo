import type { WorkspaceDescriptorPayload } from "@getpaseo/protocol/messages";
import type { OutputSchema } from "../../output/index.js";
export interface WorkspaceRow {
    workspaceId: string;
    project: string;
    name: string;
    isolation: "local" | "worktree";
    cwd: string;
    background: boolean;
}
export declare const workspaceSchema: OutputSchema<WorkspaceRow>;
/** `--background` listings add a column so hidden workspaces stand out. */
export declare const workspaceWithBackgroundSchema: OutputSchema<WorkspaceRow>;
export declare function toWorkspaceRow(workspace: WorkspaceDescriptorPayload): WorkspaceRow;
//# sourceMappingURL=shared.d.ts.map