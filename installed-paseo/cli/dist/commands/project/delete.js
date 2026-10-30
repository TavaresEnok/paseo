import { buildDaemonConnectionCommandError, connectToDaemon } from "../../utils/client.js";
const projectDeleteSchema = {
    idField: "projectId",
    columns: [
        { header: "PROJECT ID", field: "projectId", width: 20 },
        {
            header: "REMOVED WORKSPACES",
            field: (result) => result.removedWorkspaceIds.length,
            width: 18,
        },
    ],
};
export async function runDeleteCommand(projectId, options, _command) {
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        throw buildDaemonConnectionCommandError({ target: options.daemonTarget, error });
    });
    try {
        const result = await client.removeProject(projectId);
        return {
            type: "single",
            data: { projectId, removedWorkspaceIds: result.removedWorkspaceIds },
            schema: projectDeleteSchema,
        };
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error)
            throw error;
        const message = error instanceof Error ? error.message : String(error);
        throw { code: "PROJECT_DELETE_FAILED", message };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=delete.js.map