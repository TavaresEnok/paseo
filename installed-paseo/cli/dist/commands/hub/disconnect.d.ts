import type { Command } from "commander";
import type { HubDaemonConnection } from "./daemon-client.js";
import { type HubReporter } from "./reporter.js";
interface HubDisconnectOptions {
    force?: boolean;
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
    json?: boolean;
}
interface HubDisconnectDependencies {
    daemon: HubDaemonConnection;
    reporter: HubReporter;
}
export declare function runHubDisconnect(options: HubDisconnectOptions, dependencies: HubDisconnectDependencies): Promise<import("../../output/types.js").ListResult<import("./status-output.js").HubRow>>;
export declare function addHubDisconnectCommand(parent: Command, dependencies: HubDisconnectDependencies): void;
export {};
//# sourceMappingURL=disconnect.d.ts.map