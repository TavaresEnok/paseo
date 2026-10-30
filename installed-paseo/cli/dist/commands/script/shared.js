import { resolve } from "node:path";
import { connectToDaemon, getDaemonHost } from "../../utils/client.js";
export async function connectWorkspaceScriptClient(target) {
    const daemonHost = getDaemonHost({ target });
    try {
        const client = await connectToDaemon({ target });
        // COMPAT(workspaceScriptManagement): added in v0.1.105, remove gate after 2027-01-10.
        if (!client.getLastServerInfoMessage()?.features?.workspaceScriptManagement) {
            await client.close().catch(() => { });
            throw {
                code: "DAEMON_UPDATE_REQUIRED",
                message: "Update the host to use workspace script management.",
            };
        }
        return client;
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error && "message" in error) {
            throw error;
        }
        const message = error instanceof Error ? error.message : String(error);
        throw {
            code: "DAEMON_NOT_RUNNING",
            message: `Cannot connect to daemon at ${daemonHost}: ${message}`,
            details: "Start the daemon with: paseo daemon start",
        };
    }
}
export async function resolveWorkspaceScriptWorkspaceId(client, options) {
    if (options.workspace) {
        return options.workspace;
    }
    const cwd = resolve(options.cwd ?? process.cwd());
    const payload = await client.fetchWorkspaces({ page: { limit: 200 } });
    const matches = payload.entries.filter((workspace) => resolve(workspace.workspaceDirectory) === cwd);
    if (matches.length === 1) {
        return matches[0].id;
    }
    if (matches.length > 1) {
        throw {
            code: "WORKSPACE_AMBIGUOUS",
            message: `Multiple workspaces use ${cwd}`,
            details: "Pass --workspace <workspace-id> to select one.",
        };
    }
    throw {
        code: "WORKSPACE_NOT_FOUND",
        message: `No Paseo workspace found for ${cwd}`,
        details: "Open the directory in Paseo first, or pass --workspace <workspace-id>.",
    };
}
export function toWorkspaceScriptCommandError(code, action, error) {
    if (error && typeof error === "object" && "code" in error && "message" in error) {
        return error;
    }
    const message = error instanceof Error ? error.message : String(error);
    return { code, message: `Failed to ${action}: ${message}` };
}
//# sourceMappingURL=shared.js.map