import type { PersistedWorkspaceRecord } from "./workspace-registry.js";
import type { WorkspaceSetupSnapshot } from "@getpaseo/protocol/messages";
type Listener = (workspaceId: string, snapshot: WorkspaceSetupSnapshot, statusChanged: boolean) => void;
/** Daemon-owned setup snapshots, shared by sessions; output never invalidates the directory. */
export declare class WorkspaceSetupObservation {
    private readonly listeners;
    private readonly statuses;
    private readonly snapshots;
    get(workspaceId: string): WorkspaceSetupSnapshot | undefined;
    cache(workspaceId: string, snapshot: WorkspaceSetupSnapshot): void;
    publish(workspaceId: string, snapshot: WorkspaceSetupSnapshot): void;
    status(workspace: Pick<PersistedWorkspaceRecord, "workspaceId" | "untrustedSource">): WorkspaceSetupSnapshot["status"] | null;
    private summary;
    subscribe(listener: Listener): () => void;
}
export {};
//# sourceMappingURL=workspace-setup-observation.d.ts.map