import { connectToDaemon, getDaemonHost } from "../../utils/client.js";
const workspaceSetupSchema = {
    idField: "workspaceId",
    columns: [
        { header: "WORKSPACE ID", field: "workspaceId", width: 20 },
        { header: "STATUS", field: "status", width: 18 },
    ],
};
export async function runSetupCommand(workspaceId, options, _command) {
    const host = getDaemonHost({ target: options.daemonTarget });
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        throw {
            code: "DAEMON_NOT_RUNNING",
            message: `Cannot connect to daemon at ${host}: ${error instanceof Error ? error.message : String(error)}`,
        };
    });
    try {
        // COMPAT(workspaceSetupRun): added in v0.7.3, remove gate after 2027-09-02.
        if (!client.getLastServerInfoMessage()?.features?.workspaceSetupRun) {
            throw { code: "DAEMON_UPDATE_REQUIRED", message: "Update the host to run workspace setup." };
        }
        const payload = await client.runWorkspaceSetup(workspaceId);
        if (payload.error)
            throw new Error(payload.error);
        return {
            type: "single",
            data: { workspaceId, status: payload.started ? "started" : "already_allowed" },
            schema: workspaceSetupSchema,
        };
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error)
            throw error;
        const message = error instanceof Error ? error.message : String(error);
        throw { code: "WORKSPACE_SETUP_FAILED", message };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=setup.js.map