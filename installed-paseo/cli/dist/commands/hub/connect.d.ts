import type { Command } from "commander";
import type { HubHttpClient } from "./hub-client/index.js";
import type { HubCredentialStore } from "./credentials.js";
import type { HubDaemonConnection } from "./daemon-client.js";
import { type HubReporter } from "./reporter.js";
interface HubConnectOptions {
    apiKey?: string;
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
    json?: boolean;
    permission?: readonly string[];
    permissions?: readonly string[];
}
interface HubConnectDependencies {
    env: Readonly<Record<string, string | undefined>>;
    credentials: HubCredentialStore;
    hub: Pick<HubHttpClient, "issueEnrollmentToken">;
    daemon: HubDaemonConnection;
    reporter: HubReporter;
}
export declare function runHubConnect(originInput: string | undefined, options: HubConnectOptions, dependencies: HubConnectDependencies): Promise<import("../../output/types.js").ListResult<import("./status-output.js").HubRow>>;
export declare function addHubConnectCommand(parent: Command, dependencies: HubConnectDependencies): void;
export {};
//# sourceMappingURL=connect.d.ts.map