import type { Command } from "commander";
import { type SingleResult } from "../../output/index.js";
import type { HubCredentialStore } from "./credentials.js";
import type { HubHttpClient } from "./hub-client/index.js";
import { type HubReporter } from "./reporter.js";
interface HubExportResult {
    origin: string;
    directory: string;
    exported: number;
    unchanged: number;
}
export interface HubExportOptions {
    hub?: string;
    apiKey?: string;
    force?: boolean;
    json?: boolean;
}
interface HubExportDependencies {
    env: Readonly<Record<string, string | undefined>>;
    credentials: HubCredentialStore;
    hub: Pick<HubHttpClient, "listTriggers">;
    reporter: HubReporter;
    cwd(): string;
}
export declare function runHubExport(directoryInput: string | undefined, options: HubExportOptions, dependencies: HubExportDependencies): Promise<SingleResult<HubExportResult>>;
export declare function addHubExportCommand(parent: Command, dependencies: HubExportDependencies): void;
export {};
//# sourceMappingURL=export.d.ts.map