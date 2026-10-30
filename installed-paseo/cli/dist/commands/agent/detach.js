import { connectToDaemon, resolveAgentId } from "../../utils/client.js";
const detachSchema = {
    idField: "agentId",
    columns: [
        { header: "AGENT ID", field: "agentId" },
        { header: "STATUS", field: "status" },
    ],
};
export async function runDetachCommand(agentIdArg, options, _command) {
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const payload = await client.fetchAgents({ filter: { includeArchived: true } });
        const agentId = resolveAgentId(agentIdArg, payload.entries.map((entry) => entry.agent));
        if (!agentId) {
            throw {
                code: "AGENT_NOT_FOUND",
                message: `Agent not found: ${agentIdArg}`,
            };
        }
        await client.detachAgent(agentId);
        return { type: "single", data: { agentId, status: "detached" }, schema: detachSchema };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=detach.js.map