import type { ModelInfo, Query } from "@anthropic-ai/claude-agent-sdk";
import type { ProviderRuntimeSettings } from "../../provider-launch-config.js";
import { type ClaudeQueryInput, type ClaudeQueryContext } from "./query.js";
interface ClaudeModelDiscoveryOptions {
    resolveBinary: () => Promise<string>;
    runtimeSettings?: ProviderRuntimeSettings;
    env: NodeJS.ProcessEnv;
    signal?: AbortSignal;
}
type OpenDiscoveryQuery = (input: ClaudeQueryInput, context: ClaudeQueryContext) => Pick<Query, "supportedModels" | "close">;
export declare function discoverClaudeModels(options: ClaudeModelDiscoveryOptions, openQuery?: OpenDiscoveryQuery): Promise<ModelInfo[]>;
export {};
//# sourceMappingURL=model-discovery.d.ts.map