import type { WorkspaceProjectDescriptorPayload } from "@getpaseo/protocol/messages";
import type { OutputSchema } from "../../output/index.js";
export interface ProjectRow {
    projectId: string;
    name: string;
    kind: "git" | "non_git" | "directory";
    path: string;
}
export declare const projectSchema: OutputSchema<ProjectRow>;
export declare function toProjectRow(project: WorkspaceProjectDescriptorPayload): ProjectRow;
//# sourceMappingURL=shared.d.ts.map