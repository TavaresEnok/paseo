import { connectWorkspaceScriptClient, resolveWorkspaceScriptWorkspaceId, toWorkspaceScriptCommandError, } from "./shared.js";
import { workspaceScriptSchema } from "./schema.js";
export async function runLsCommand(options, _command) {
    const client = await connectWorkspaceScriptClient(options.daemonTarget);
    try {
        const workspaceId = await resolveWorkspaceScriptWorkspaceId(client, options);
        const payload = await client.listWorkspaceScripts(workspaceId);
        if (payload.error) {
            throw new Error(payload.error);
        }
        return { type: "list", data: payload.scripts ?? [], schema: workspaceScriptSchema };
    }
    catch (error) {
        throw toWorkspaceScriptCommandError("WORKSPACE_SCRIPT_LIST_FAILED", "list workspace scripts", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=ls.js.map