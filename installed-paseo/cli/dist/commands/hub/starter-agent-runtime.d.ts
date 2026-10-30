import type { ProviderSnapshotEntry } from "@getpaseo/protocol/agent-types";
export interface HubStarterAgentRuntime {
    provider: string;
    model: string;
    mode?: string;
}
export interface HubStarterAgentProvider {
    id: string;
    label: string;
    models: readonly HubStarterAgentModel[];
    modes: readonly HubStarterAgentMode[];
}
export interface HubStarterAgentModel {
    id: string;
    label: string;
    suggested: boolean;
}
export interface HubStarterAgentMode {
    id: string;
    label: string;
    suggested: boolean;
}
export type HubStarterAgentProviderSnapshotState = {
    kind: "ready";
    providers: readonly HubStarterAgentProvider[];
} | {
    kind: "loading";
} | {
    kind: "unavailable";
};
export declare function availableStarterAgentProviders(entries: readonly ProviderSnapshotEntry[]): HubStarterAgentProvider[];
export declare function starterAgentProviderSnapshotState(entries: readonly ProviderSnapshotEntry[]): HubStarterAgentProviderSnapshotState;
export declare function suggestedStarterAgentChoice<T extends {
    suggested: boolean;
}>(choices: readonly T[]): T | undefined;
export declare function selectedStarterAgentRuntime(provider: HubStarterAgentProvider, modelId: string, modeId?: string): HubStarterAgentRuntime | undefined;
//# sourceMappingURL=starter-agent-runtime.d.ts.map