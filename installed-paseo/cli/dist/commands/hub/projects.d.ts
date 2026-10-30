import type { Command } from "commander";
import { type SingleResult } from "../../output/index.js";
import type { HubHttpClient, HubProject } from "./hub-client/index.js";
import type { HubCredentialStore } from "./credentials.js";
import { type HubReporter } from "./reporter.js";
interface HubProjectsResult {
    origin: string;
    projects: HubProject[];
}
export interface HubProjectsOptions {
    hub?: string;
    apiKey?: string;
    json?: boolean;
}
interface HubProjectsDependencies {
    env: Readonly<Record<string, string | undefined>>;
    credentials: HubCredentialStore;
    hub: Pick<HubHttpClient, "listProjects">;
    reporter: HubReporter;
}
export declare function runHubProjects(options: HubProjectsOptions, dependencies: HubProjectsDependencies): Promise<SingleResult<HubProjectsResult>>;
export declare function addHubProjectsCommand(parent: Command, dependencies: HubProjectsDependencies): void;
export {};
//# sourceMappingURL=projects.d.ts.map