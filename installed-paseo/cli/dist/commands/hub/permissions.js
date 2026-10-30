import { withOutput } from "../../output/index.js";
import { addJsonAndDaemonHostOptions } from "../../utils/command-options.js";
import { withHubDaemon } from "./daemon-client.js";
import { reportHubProgress } from "./reporter.js";
import { hubStatusResult } from "./status-output.js";
const schema = {
    idField: "permission",
    columns: [
        { header: "PERMISSION", field: "permission" },
        { header: "DESCRIPTION", field: "description" },
    ],
};
export function runHubPermissionsList(options, dependencies) {
    return withHubDaemon(dependencies.daemon, options.daemonTarget, async (client) => {
        const status = (await client.getHubStatus()).status;
        requireConnectedHub(status);
        return {
            type: "list",
            data: status.permissions.map((permission) => ({
                permission,
                description: describePermission(permission),
            })),
            schema,
        };
    });
}
export function runHubPermissionChange(operation, permission, options, dependencies) {
    return withHubDaemon(dependencies.daemon, options.daemonTarget, async (client) => {
        const current = (await client.getHubStatus()).status;
        requireConnectedHub(current);
        const response = await client.updateHubPermissions(operation === "grant" ? { grant: [permission] } : { revoke: [permission] });
        reportHubProgress(dependencies.reporter, options, `${operation === "grant" ? "Granted" : "Revoked"} ${permission} ${operation === "grant" ? "to" : "from"} ${response.status.hubOrigin}`);
        return hubStatusResult(response.status);
    });
}
export function addHubPermissionsCommand(parent, dependencies) {
    const permissions = parent
        .command("permissions")
        .description("Manage this Hub's daemon permissions");
    addJsonAndDaemonHostOptions(permissions.command("list")).action(withOutput(async (...args) => {
        const options = args.at(-2);
        return runHubPermissionsList(options, dependencies);
    }));
    for (const operation of ["grant", "revoke"]) {
        addJsonAndDaemonHostOptions(permissions.command(operation).argument("<permission>", "Daemon permission")).action(withOutput(async (...args) => {
            const permission = args[0];
            const options = args.at(-2);
            return runHubPermissionChange(operation, permission, options, dependencies);
        }));
    }
}
function requireConnectedHub(status) {
    if (status.hubOrigin === null ||
        (status.state !== "connected" && status.state !== "reconnecting")) {
        throw new Error("This daemon is not connected to a Hub");
    }
}
function describePermission(permission) {
    return permission === "hub.execute" ? "Run agents for Hub automations" : permission;
}
//# sourceMappingURL=permissions.js.map