import type { Command } from "commander";
import { type ListResult, type SingleResult } from "../../output/index.js";
import { HubHttpClient, type HubInstallResult, type HubTriggerInstallationResult, type HubTriggerValidationResult, type HubValidationResult } from "./hub-client/index.js";
import { type HubCredentialStore } from "./credentials.js";
import { type HubDeployBundle } from "./deploy-bundle.js";
import { type HubDeployTrigger } from "./deploy-triggers.js";
import { type HubReporter } from "./reporter.js";
export interface HubDeployOptions {
    project?: string;
    hub?: string;
    apiKey?: string;
    dryRun?: boolean;
    json?: boolean;
}
export interface HubDeployEnvironment {
    cwd: string;
    env: Readonly<Record<string, string | undefined>>;
    credentials?: HubCredentialStore;
    hub?: Pick<HubHttpClient, "installConfiguration" | "validateConfiguration" | "installTrigger" | "validateTrigger">;
    reporter?: HubReporter;
}
export interface HubDeployCommandDependencies {
    env: Readonly<Record<string, string | undefined>>;
    credentials: HubCredentialStore;
    hub: Pick<HubHttpClient, "installConfiguration" | "validateConfiguration" | "installTrigger" | "validateTrigger">;
    reporter: HubReporter;
    cwd(): string;
}
interface HubDeployResult extends HubInstallResult {
    origin: string;
    workflows: number;
}
interface HubDryRunResult extends HubValidationResult {
    origin: string;
    workflows: number;
}
interface HubTriggerDeployResult extends HubTriggerInstallationResult {
    origin: string;
    path: string;
}
interface HubTriggerDryRunResult extends HubTriggerValidationResult {
    origin: string;
    path: string;
}
export declare function runHubDeploy(options: HubDeployOptions, environment?: HubDeployEnvironment): Promise<SingleResult<HubDeployResult> | SingleResult<HubDryRunResult> | ListResult<HubTriggerDeployResult> | ListResult<HubTriggerDryRunResult>>;
export declare function runHubDeployTriggers(options: HubDeployOptions, triggers: readonly HubDeployTrigger[], environment: HubDeployEnvironment): Promise<ListResult<HubTriggerDeployResult> | ListResult<HubTriggerDryRunResult>>;
export declare function runHubDeployBundle(options: HubDeployOptions, deployInput: HubDeployBundle, environment: HubDeployEnvironment): Promise<SingleResult<HubDeployResult> | SingleResult<HubDryRunResult>>;
export declare function addHubDeployCommand(hub: Command, dependencies: HubDeployCommandDependencies): void;
export {};
//# sourceMappingURL=deploy.d.ts.map