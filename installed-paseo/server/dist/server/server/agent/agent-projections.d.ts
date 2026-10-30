import type { AgentListItemPayload, AgentSnapshotPayload, RecentProviderSessionDescriptorPayload } from "../messages.js";
import type { StoredAgentRecord } from "./agent-storage.js";
import type { AgentProvider, AgentRuntimeInfo, ImportableProviderSession } from "./agent-sdk-types.js";
import type { ManagedAgent } from "./agent-manager.js";
export type { ManagedAgent };
interface ProjectionOptions {
    title?: string | null;
    createdAt?: string;
    internal?: boolean;
    /**
     * Archive timestamp, supplied by a caller holding the stored record. A live
     * managed agent cannot know this: an archived agent is resumed back into
     * memory to serve a history read, so being in the manager is not evidence
     * that it is active. Storage stays the single owner.
     */
    archivedAt?: string | null;
}
interface RecentProviderSessionProjectionOptions {
    providerLabel: string;
}
export declare function resolveEffectiveThinkingOptionId(options: {
    runtimeInfo?: AgentRuntimeInfo | null;
    configuredThinkingOptionId?: string | null;
}): string | null;
export declare function toStoredAgentRecord(agent: ManagedAgent, options?: ProjectionOptions): StoredAgentRecord;
export declare function toAgentPayload(agent: ManagedAgent, options?: ProjectionOptions): AgentSnapshotPayload;
export declare function buildStoredAgentPayload(record: StoredAgentRecord, validProviders: Iterable<AgentProvider>): AgentSnapshotPayload;
export declare function toAgentListItemPayload(agent: AgentSnapshotPayload): AgentListItemPayload;
export declare function selectAgentListItems(agents: readonly AgentSnapshotPayload[], options?: {
    cwd?: string;
    statuses?: AgentSnapshotPayload["status"][];
    sinceHours?: number;
    limit?: number;
}): AgentListItemPayload[];
export declare function toRecentProviderSessionDescriptorPayload(session: ImportableProviderSession & {
    provider: string;
}, options: RecentProviderSessionProjectionOptions): RecentProviderSessionDescriptorPayload;
//# sourceMappingURL=agent-projections.d.ts.map