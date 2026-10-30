import { connectToDaemon, getDaemonHost } from "../../utils/client.js";
const workspaceArchiveSchema = {
    idField: "workspaceId",
    columns: [
        { header: "WORKSPACE ID", field: "workspaceId", width: 20 },
        { header: "STATUS", field: "status", width: 10 },
        { header: "ARCHIVED AT", field: "archivedAt", width: 26 },
    ],
};
export async function runArchiveCommand(workspaceId, options, _command) {
    const host = getDaemonHost({ target: options.daemonTarget });
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        throw {
            code: "DAEMON_NOT_RUNNING",
            message: `Cannot connect to daemon at ${host}: ${message}`,
        };
    });
    try {
        const payload = await client.archiveWorkspace(workspaceId);
        if (payload.error) {
            throw new Error(payload.error);
        }
        if (!payload.archivedAt) {
            throw new Error("Workspace archive did not return an archive timestamp");
        }
        return {
            type: "single",
            data: { workspaceId, status: "archived", archivedAt: payload.archivedAt },
            schema: workspaceArchiveSchema,
        };
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error)
            throw error;
        const message = error instanceof Error ? error.message : String(error);
        throw { code: "WORKSPACE_ARCHIVE_FAILED", message };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=archive.js.map