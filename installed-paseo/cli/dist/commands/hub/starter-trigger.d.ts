import type { HubConfigurationResources } from "./hub-client/index.js";
import type { HubInitProvider } from "./init-plan.js";
export interface HubStarterTriggerConnection {
    id: string;
    label: string;
    provider: HubInitProvider;
    filters: Readonly<Record<string, string>>;
}
export declare function availableStarterTriggerConnections(resources: HubConfigurationResources, githubRepository?: string): HubStarterTriggerConnection[];
//# sourceMappingURL=starter-trigger.d.ts.map