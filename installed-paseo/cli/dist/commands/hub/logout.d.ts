import type { Command } from "commander";
import { type SingleResult } from "../../output/index.js";
import type { HubCredentialStore } from "./credentials.js";
import type { HubDaemonConnection } from "./daemon-client.js";
import { type HubReporter } from "./reporter.js";
interface HubLogoutResult {
    origin: string | null;
    status: "logged_out" | "not_logged_in";
    daemonDisconnected: boolean;
    warning?: string;
}
interface HubLogoutOptions {
    disconnectDaemon?: boolean;
    force?: boolean;
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
    json?: boolean;
}
interface HubLogoutDependencies {
    credentials: HubCredentialStore;
    daemon: HubDaemonConnection;
    isInteractive(): boolean;
    confirmDisconnect(origin: string): Promise<boolean>;
    reporter: HubReporter;
}
export declare function runHubLogout(options: HubLogoutOptions, dependencies: HubLogoutDependencies): Promise<SingleResult<HubLogoutResult>>;
export declare function addHubLogoutCommand(parent: Command, dependencies: HubLogoutDependencies): void;
export declare const productionLogoutPrompt: {
    isInteractive: () => boolean;
    confirmDisconnect(origin: string): Promise<boolean>;
};
export {};
//# sourceMappingURL=logout.d.ts.map