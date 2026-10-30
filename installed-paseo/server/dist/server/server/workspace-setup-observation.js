/** Daemon-owned setup snapshots, shared by sessions; output never invalidates the directory. */
export class WorkspaceSetupObservation {
    constructor() {
        this.listeners = new Set();
        this.statuses = new Map();
        this.snapshots = new Map();
    }
    get(workspaceId) {
        return this.snapshots.get(workspaceId);
    }
    cache(workspaceId, snapshot) {
        this.snapshots.set(workspaceId, snapshot);
    }
    publish(workspaceId, snapshot) {
        const status = this.summary(snapshot);
        const statusChanged = (this.statuses.get(workspaceId) ?? null) !== status;
        this.statuses.set(workspaceId, status);
        this.snapshots.set(workspaceId, snapshot);
        for (const listener of this.listeners)
            listener(workspaceId, snapshot, statusChanged);
    }
    status(workspace) {
        const snapshot = this.snapshots.get(workspace.workspaceId);
        if (snapshot)
            return this.summary(snapshot);
        return workspace.untrustedSource ? "blocked" : null;
    }
    summary(snapshot) {
        if (snapshot.status === "failed" ||
            snapshot.status === "blocked" ||
            snapshot.error !== null ||
            snapshot.detail.commands.length > 0)
            return snapshot.status;
        return null;
    }
    subscribe(listener) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }
}
//# sourceMappingURL=workspace-setup-observation.js.map