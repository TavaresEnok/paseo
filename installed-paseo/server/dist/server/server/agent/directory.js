/** Public agent discovery owns workspace visibility for live and durable records. */
export class AgentDirectory {
    constructor(deps) {
        this.deps = deps;
    }
    /** Human prompt recency includes archived/unavailable agents without projecting their UI payloads. */
    async workspaceLastUserMessageTimes() {
        const live = this.deps.manager.listAgents();
        const liveIds = new Set(live.map((agent) => agent.id));
        const times = new Map();
        const record = (workspaceId, at) => {
            if (!workspaceId || !at)
                return;
            const previous = times.get(workspaceId);
            if (!previous || at > previous)
                times.set(workspaceId, at);
        };
        for (const agent of await this.deps.storage.list()) {
            if (!agent.internal && !liveIds.has(agent.id))
                record(agent.workspaceId, agent.lastUserMessageAt);
        }
        for (const agent of live) {
            if (!agent.internal)
                record(agent.workspaceId, agent.lastUserMessageAt?.toISOString());
        }
        return times;
    }
    async includes(agent, includeBackground = false) {
        if (agent.internal)
            return false;
        if (includeBackground || !agent.workspaceId)
            return true;
        return !(await this.deps.workspaces.get(agent.workspaceId))?.background;
    }
    async list(filter) {
        const live = this.deps.manager.listAgents();
        const liveIds = new Set(live.map((agent) => agent.id));
        const labels = Object.entries(filter?.labels ?? {});
        const backgroundIds = new Set(filter?.includeBackground
            ? []
            : (await this.deps.workspaces.list())
                .filter((workspace) => workspace.background)
                .map((workspace) => workspace.workspaceId));
        const matches = (agent) => (filter?.includeArchived || !agent.archivedAt) &&
            (filter?.includeBackground || !agent.workspaceId || !backgroundIds.has(agent.workspaceId)) &&
            labels.every(([key, value]) => agent.labels?.[key] === value);
        const stored = (await this.deps.storage.list())
            .filter((record) => !record.internal && !liveIds.has(record.id) && matches(record))
            .filter((record) => filter?.includeUnavailablePersisted || this.deps.isStoredProviderAvailable(record))
            .map((record) => this.deps.projectStored(record));
        const active = await Promise.all(live.filter(matches).map((agent) => this.deps.projectLive(agent)));
        return [...active, ...stored]
            .filter(matches)
            .filter((agent) => this.deps.isProviderVisible(agent.provider));
    }
}
//# sourceMappingURL=directory.js.map