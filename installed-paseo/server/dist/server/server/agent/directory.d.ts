import type { AgentSnapshotPayload } from "../messages.js";
import type { WorkspaceRegistry } from "../workspace-registry.js";
import type { AgentManager, ManagedAgent } from "./agent-manager.js";
import type { AgentStorage, StoredAgentRecord } from "./agent-storage.js";
/** Public agent discovery owns workspace visibility for live and durable records. */
export declare class AgentDirectory {
    private readonly deps;
    constructor(deps: {
        manager: Pick<AgentManager, "listAgents">;
        storage: Pick<AgentStorage, "list">;
        workspaces: Pick<WorkspaceRegistry, "get" | "list">;
        projectLive(agent: ManagedAgent): Promise<AgentSnapshotPayload>;
        projectStored(record: StoredAgentRecord): AgentSnapshotPayload;
        isProviderVisible(provider: string): boolean;
        isStoredProviderAvailable(record: StoredAgentRecord): boolean;
    });
    /** Human prompt recency includes archived/unavailable agents without projecting their UI payloads. */
    workspaceLastUserMessageTimes(): Promise<Map<string, string>>;
    includes(agent: Pick<AgentSnapshotPayload, "workspaceId" | "internal">, includeBackground?: boolean): Promise<boolean>;
    list(filter?: {
        labels?: Record<string, string>;
        includeArchived?: boolean;
        includeBackground?: boolean;
        includeUnavailablePersisted?: boolean;
    }): Promise<AgentSnapshotPayload[]>;
}
//# sourceMappingURL=directory.d.ts.map