import { connectToDaemon, getDaemonHost } from "../../utils/client.js";
const workspaceRenameSchema = {
    idField: "workspaceId",
    columns: [
        { header: "WORKSPACE ID", field: "workspaceId", width: 20 },
        { header: "TITLE", field: "title", width: 30 },
    ],
};
/**
 * Resolve the title to send to the daemon. Null clears the override and
 * reverts the workspace to its branch- or directory-derived name.
 */
export function resolveWorkspaceTitle(input) {
    const title = input.title?.trim() ?? "";
    if (input.reset) {
        if (input.title !== undefined) {
            throw {
                code: "INVALID_OPTIONS",
                message: "--reset cannot be combined with a title",
                details: "Pass a title to rename the workspace, or --reset to revert to the derived name",
            };
        }
        return null;
    }
    if (title.length === 0) {
        throw {
            code: "MISSING_TITLE",
            message: "Title cannot be empty",
            details: "Usage: paseo workspace rename <workspace-id> <title> | --reset",
        };
    }
    return title;
}
export async function runRenameCommand(workspaceId, titleArg, options, _command) {
    const title = resolveWorkspaceTitle({ title: titleArg, reset: options.reset });
    const host = getDaemonHost({ target: options.daemonTarget });
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        throw {
            code: "DAEMON_NOT_RUNNING",
            message: `Cannot connect to daemon at ${host}: ${message}`,
            details: "Start the daemon with: paseo daemon start",
        };
    });
    try {
        const applied = await client.setWorkspaceTitle(workspaceId, title);
        return {
            type: "single",
            data: { workspaceId, title: applied.title },
            schema: workspaceRenameSchema,
        };
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error)
            throw error;
        const message = error instanceof Error ? error.message : String(error);
        throw { code: "WORKSPACE_RENAME_FAILED", message };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=rename.js.map