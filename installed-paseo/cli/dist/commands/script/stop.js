import { connectWorkspaceScriptClient, resolveWorkspaceScriptWorkspaceId, toWorkspaceScriptCommandError, } from "./shared.js";
import { workspaceScriptSchema } from "./schema.js";
export async function runStopCommand(scriptName, options, _command) {
    const client = await connectWorkspaceScriptClient(options.daemonTarget);
    try {
        const workspaceId = await resolveWorkspaceScriptWorkspaceId(client, options);
        const payload = await client.stopWorkspaceScript(workspaceId, scriptName);
        if (payload.error || !payload.script) {
            throw {
                code: "WORKSPACE_SCRIPT_STOP_FAILED",
                message: payload.error ?? `Script '${scriptName}' did not return status metadata`,
            };
        }
        return { type: "single", data: payload.script, schema: workspaceScriptSchema };
    }
    catch (error) {
        throw toWorkspaceScriptCommandError("WORKSPACE_SCRIPT_STOP_FAILED", "stop workspace script", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=stop.js.map