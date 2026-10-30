import type { Command } from "commander";
import { type ListResult } from "../../output/index.js";
import type { HubDaemonConnection } from "./daemon-client.js";
import { type HubReporter } from "./reporter.js";
interface HubPermissionsOptions {
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
    json?: boolean;
}
interface HubPermissionsDependencies {
    daemon: HubDaemonConnection;
    reporter: HubReporter;
}
interface PermissionRow {
    permission: string;
    description: string;
}
export declare function runHubPermissionsList(options: HubPermissionsOptions, dependencies: HubPermissionsDependencies): Promise<ListResult<PermissionRow>>;
export declare function runHubPermissionChange(operation: "grant" | "revoke", permission: string, options: HubPermissionsOptions, dependencies: HubPermissionsDependencies): Promise<ListResult<import("./status-output.js").HubRow>>;
export declare function addHubPermissionsCommand(parent: Command, dependencies: HubPermissionsDependencies): void;
export {};
//# sourceMappingURL=permissions.d.ts.map