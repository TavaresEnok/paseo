import type { HubBundleFile } from "../deploy-bundle.js";
import { type CliAuthorization, type CliAuthorizationPoll, type HubInstallResult, type HubConfigurationResources, type HubProject, type HubTrigger, type HubTriggerInstallationResult, type HubTriggerValidationResult, type HubValidationResult } from "./internal/contracts.js";
export type { CliAuthorization, CliAuthorizationPoll, HubInstallResult, HubConfigurationResources, HubProject, HubTrigger, HubTriggerInstallationResult, HubTriggerValidationResult, HubValidationResult, } from "./internal/contracts.js";
interface HubConfigurationInput {
    origin: string;
    apiKey: string;
    projectSlug: string;
    files: readonly HubBundleFile[];
}
export declare class HubHttpClient {
    startCliAuthorization(origin: string): Promise<CliAuthorization>;
    pollCliAuthorization(origin: string, deviceCode: string, timeoutMilliseconds: number): Promise<CliAuthorizationPoll>;
    listProjects(origin: string, apiKey: string): Promise<HubProject[]>;
    listTriggers(origin: string, apiKey: string): Promise<HubTrigger[]>;
    validateTrigger(origin: string, apiKey: string, yaml: string): Promise<HubTriggerValidationResult>;
    installTrigger(origin: string, apiKey: string, yaml: string): Promise<HubTriggerInstallationResult>;
    listConfigurationResources(origin: string, apiKey: string): Promise<HubConfigurationResources>;
    installConfiguration(input: HubConfigurationInput): Promise<HubInstallResult>;
    validateConfiguration(input: HubConfigurationInput): Promise<HubValidationResult>;
    issueEnrollmentToken(origin: string, apiKey: string): Promise<string>;
}
//# sourceMappingURL=index.d.ts.map