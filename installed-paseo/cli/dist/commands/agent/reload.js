import { connectToDaemon, resolveAgentId } from "../../utils/client.js";
export const reloadSchema = {
    idField: "agentId",
    columns: [
        { header: "AGENT ID", field: "agentId" },
        { header: "STATUS", field: "status" },
        { header: "TIMELINE", field: "timelineSize" },
    ],
};
export function addReloadOptions(cmd) {
    return cmd
        .description("Reload an agent (restarts the underlying process)")
        .argument("<id>", "Agent ID, prefix, or name");
}
export async function runReloadCommand(agentIdArg, options, _command) {
    if (!agentIdArg || agentIdArg.trim().length === 0) {
        const error = {
            code: "MISSING_AGENT_ID",
            message: "Agent ID is required",
            details: "Usage: paseo agent reload <id-or-name>",
        };
        throw error;
    }
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const agentsPayload = await client.fetchAgents({ filter: { includeArchived: true } });
        const agents = agentsPayload.entries.map((entry) => entry.agent);
        const agentId = resolveAgentId(agentIdArg, agents);
        if (!agentId) {
            const error = {
                code: "AGENT_NOT_FOUND",
                message: `Agent not found: ${agentIdArg}`,
                details: 'Use "paseo ls" to list available agents',
            };
            throw error;
        }
        const result = await client.refreshAgent(agentId);
        await client.close();
        return {
            type: "single",
            data: {
                agentId: result.agentId,
                status: "reloaded",
                timelineSize: result.timelineSize ?? 0,
            },
            schema: reloadSchema,
        };
    }
    catch (err) {
        await client.close().catch(() => { });
        if (err && typeof err === "object" && "code" in err) {
            throw err;
        }
        const message = err instanceof Error ? err.message : String(err);
        const error = {
            code: "RELOAD_FAILED",
            message: `Failed to reload agent: ${message}`,
        };
        throw error;
    }
}
//# sourceMappingURL=reload.js.map