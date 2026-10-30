import type { HubStatus } from "./daemon-client.js";
import type { HubStarterAgentRuntime } from "./starter-agent-runtime.js";
export type HubInitProvider = "github" | "slack" | "discord";
export type HubInitConnectionResolution = {
    kind: "connected";
    daemonId: string;
} | {
    kind: "pending";
    state: "connecting" | "reconnecting";
} | {
    kind: "connect";
} | {
    kind: "conflict";
    origin: string;
};
export interface HubInitScaffoldInput {
    cwd: string;
    daemonSlug: string;
    agent: HubStarterAgentRuntime & {
        mode: string;
    };
    provider: HubInitProvider;
    providerFilters: Readonly<Record<string, string>>;
}
export interface HubInitScaffold {
    triggerPath: string;
    trigger: string;
    testAction: string;
}
export declare function hubLoginResumeCommand(step: "connect" | "init", origin: string): string;
export declare function resolveHubInitConnection(status: HubStatus, origin: string): HubInitConnectionResolution;
export declare function createHubInitScaffold(input: HubInitScaffoldInput): HubInitScaffold;
//# sourceMappingURL=init-plan.d.ts.map