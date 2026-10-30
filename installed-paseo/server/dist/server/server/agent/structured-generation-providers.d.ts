import type { AgentProvider } from "./agent-sdk-types.js";
import type { StructuredGenerationProvider } from "./agent-response-loop.js";
import type { ProviderSnapshotManager } from "./provider-snapshot-manager.js";
export interface StructuredGenerationDaemonConfig {
    metadataGeneration?: {
        providers?: Array<{
            provider: string;
            model?: string;
            thinkingOptionId?: string;
        }>;
    };
}
export interface StructuredGenerationProviderIdentifier {
    modelSubstring: string;
    thinkingOptionId?: string;
}
export declare const DEFAULT_STRUCTURED_GENERATION_PROVIDERS: readonly StructuredGenerationProviderIdentifier[];
export interface ResolveStructuredGenerationProvidersOptions {
    cwd: string;
    providerSnapshotManager: Pick<ProviderSnapshotManager, "listProviders">;
    daemonConfig?: StructuredGenerationDaemonConfig | null;
    currentSelection?: {
        provider?: AgentProvider | null;
        model?: string | null;
        thinkingOptionId?: string | null;
    };
}
/**
 * A non-empty configured list means Manual: only those models are tried, in order.
 * An empty list means Automatic: built-in defaults, then the current selection.
 */
export declare function resolveStructuredGenerationProviders(options: ResolveStructuredGenerationProvidersOptions): Promise<StructuredGenerationProvider[]>;
//# sourceMappingURL=structured-generation-providers.d.ts.map