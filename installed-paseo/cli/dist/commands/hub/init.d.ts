import type { DaemonTarget } from "../../utils/daemon-target.js";
import { select, text } from "@clack/prompts";
import type { Command } from "commander";
import type { HubCredentialStore } from "./credentials.js";
import type { HubDaemonConnection } from "./daemon-client.js";
import type { HubHttpClient } from "./hub-client/index.js";
import type { CliLoginFlow } from "./login-flow.js";
import type { HubReporter } from "./reporter.js";
export interface HubGuidedSetupEnvironment {
    daemonTarget: DaemonTarget;
    env: Readonly<Record<string, string | undefined>>;
    credentials: HubCredentialStore;
    hub: HubHttpClient;
    login: Pick<CliLoginFlow, "authorize">;
    daemon: HubDaemonConnection;
    reporter: HubReporter;
    cwd(): string;
    isInteractive?(): boolean;
    prompts?: {
        confirm(message: string, initialValue: boolean): Promise<boolean>;
        select(options: Parameters<typeof select<string>>[0]): Promise<string>;
        text(options: Parameters<typeof text>[0]): Promise<string>;
        message(value: string): void;
    };
}
interface HubGuidedSetupState {
    origin?: string;
    daemonId?: string;
    deploy?: boolean;
}
export declare function addHubInitCommand(parent: Command, environment: Omit<HubGuidedSetupEnvironment, "daemonTarget">): void;
export declare function runHubInit(environment: HubGuidedSetupEnvironment): Promise<void>;
export declare function runHubGuidedSetup(environment: HubGuidedSetupEnvironment, state?: HubGuidedSetupState): Promise<void>;
export declare function continueHubGuidedSetup(origin: string, environment: HubGuidedSetupEnvironment): Promise<void>;
export declare function githubRepositoryFromRemote(remote: string): string | undefined;
export {};
//# sourceMappingURL=init.d.ts.map