import type { WorkspaceGitRuntimeSnapshot } from "../workspace-git-service.js";
export interface WorkspaceRuntimeStore {
    get(cwd: string): WorkspaceGitRuntimeSnapshot | null;
    set(snapshot: WorkspaceGitRuntimeSnapshot): void;
    remove(cwd: string): void;
}
export declare function createWorkspaceRuntimeStore(): WorkspaceRuntimeStore;
//# sourceMappingURL=index.d.ts.map