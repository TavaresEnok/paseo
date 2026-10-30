import { connectToDaemon } from "../../utils/client.js";
import { openDesktopWithAgent } from "../open.js";
const openAgentSchema = {
    idField: "agentId",
    columns: [
        { header: "AGENT ID", field: "agentId" },
        { header: "SERVER ID", field: "serverId" },
        { header: "STATUS", field: "status" },
    ],
};
export function addOpenOptions(command) {
    return command
        .description("Open an existing agent in Paseo Desktop")
        .argument("<agent-id>", "Existing agent ID")
        .option("--server <server-id>", "Server ID (defaults to the local daemon)");
}
function toOpenError(err) {
    if (err && typeof err === "object" && "code" in err) {
        return err;
    }
    const message = err instanceof Error ? err.message : String(err);
    return { code: "OPEN_FAILED", message: `Failed to open agent: ${message}` };
}
async function resolveAgentTarget(agentId, options) {
    const explicitServerId = typeof options.server === "string" ? options.server.trim() : "";
    if (explicitServerId) {
        return { serverId: explicitServerId, agentId };
    }
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const serverId = client.getLastServerInfoMessage()?.serverId.trim();
        if (!serverId) {
            const error = {
                code: "SERVER_ID_UNAVAILABLE",
                message: "The daemon did not report a server ID.",
            };
            throw error;
        }
        const fetchResult = await client.fetchAgent({ agentId });
        if (!fetchResult) {
            const error = {
                code: "AGENT_NOT_FOUND",
                message: `Agent not found: ${agentId}`,
                details: 'Use "paseo ls" to list available agents',
            };
            throw error;
        }
        return { serverId, agentId: fetchResult.agent.id };
    }
    catch (err) {
        throw toOpenError(err);
    }
    finally {
        await client.close().catch(() => { });
    }
}
export async function runOpenCommand(agentIdArg, options, _command) {
    const agentId = agentIdArg.trim();
    if (!agentId) {
        const error = {
            code: "MISSING_AGENT_ID",
            message: "Agent ID is required.",
        };
        throw error;
    }
    const target = await resolveAgentTarget(agentId, options);
    await openDesktopWithAgent(target);
    return {
        type: "single",
        data: { ...target, status: "opened" },
        schema: openAgentSchema,
    };
}
//# sourceMappingURL=open.js.map