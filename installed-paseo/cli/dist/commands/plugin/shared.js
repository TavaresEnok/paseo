import { connectToDaemon } from "../../utils/client.js";
async function withPluginClient(target, feature, updateMessage, run) {
    const client = await connectToDaemon({ target });
    if (client.getLastServerInfoMessage()?.features?.[feature] !== true) {
        await client.close().catch(() => undefined);
        throw {
            code: "DAEMON_UPDATE_REQUIRED",
            message: updateMessage,
        };
    }
    try {
        return await run(client);
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
export async function withPluginManagementClient(target, run) {
    // COMPAT(pluginManagement): added in v0.3.1, remove gate after 2027-08-14.
    return withPluginClient(target, "pluginManagement", "Update the host to use plugin management.", run);
}
export async function withPluginLogsClient(target, run) {
    // COMPAT(pluginLogs): added in v0.4.0, remove gate after 2027-08-16.
    return withPluginClient(target, "pluginLogs", "Update the host to view plugin logs.", run);
}
export async function withPluginSourceClient(target, run) {
    // COMPAT(pluginSourceInstallation): added in v0.8.0; remove gate after 2027-03-16 once daemon floor supports source identifiers.
    return withPluginClient(target, "pluginSourceInstallation", "Update the host to install plugin sources.", run);
}
export async function withPluginUpdateClient(target, run) {
    // COMPAT(pluginSourceUpdates): added in v0.8.0; remove after 2027-03-16 once daemon floor supports reviewed updates.
    return withPluginClient(target, "pluginSourceUpdates", "Update the host to review plugin updates.", run);
}
//# sourceMappingURL=shared.js.map