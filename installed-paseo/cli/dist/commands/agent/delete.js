import { connectToDaemon } from "../../utils/client.js";
import { isSameOrDescendantPath } from "../../utils/paths.js";
export function addDeleteOptions(cmd) {
    return cmd
        .description("Delete an agent (interrupt if running, then hard-delete)")
        .argument("[id]", "Agent ID (or prefix) - optional if --all or --cwd specified")
        .option("--all", "Delete all agents")
        .option("--cwd <path>", "Delete all agents in directory");
}
export const deleteSchema = {
    idField: (item) => item.agentIds.join("\n"),
    columns: [{ header: "DELETED", field: "deletedCount" }],
};
// History includes archived agents and agents whose provider is unavailable.
async function fetchHistoryAgents(client) {
    const agents = [];
    let cursor;
    do {
        const payload = await client.fetchAgentHistory({
            page: { limit: 200, ...(cursor ? { cursor } : {}) },
        });
        agents.push(...payload.entries.map((entry) => entry.agent));
        cursor = payload.pageInfo.nextCursor ?? undefined;
    } while (cursor);
    return agents;
}
export async function runDeleteCommand(id, options, _command) {
    if (!id && !options.all && !options.cwd) {
        const error = {
            code: "MISSING_ARGUMENT",
            message: "Agent ID required unless --all or --cwd is specified",
            details: "Usage: paseo agent delete <id> | --all | --cwd <path>",
        };
        throw error;
    }
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const deletedIds = [];
        let agents;
        if (options.all || options.cwd) {
            agents = await fetchHistoryAgents(client);
            if (!options.all) {
                agents = agents.filter((a) => isSameOrDescendantPath(options.cwd, a.cwd));
            }
        }
        else {
            const fetchResult = await client.fetchAgent({ agentId: id });
            if (!fetchResult) {
                const error = {
                    code: "AGENT_NOT_FOUND",
                    message: `No agent found matching: ${id}`,
                    details: "Use `paseo ls` to list available agents",
                };
                throw error;
            }
            agents = [fetchResult.agent];
        }
        const deleteResults = await Promise.all(agents.map(async (agent) => {
            try {
                if (agent.status === "running") {
                    await client.cancelAgent(agent.id).catch(() => { });
                }
                await client.deleteAgent(agent.id);
                return { ok: true, id: agent.id };
            }
            catch (err) {
                if (err && typeof err === "object" && "code" in err)
                    throw err;
                const message = err instanceof Error ? err.message : String(err);
                return { ok: false, id: agent.id, message };
            }
        }));
        for (const result of deleteResults) {
            if (result.ok) {
                deletedIds.push(result.id);
            }
            else {
                console.error(`Warning: Failed to delete agent ${result.id.slice(0, 7)}: ${result.message}`);
            }
        }
        await client.close();
        return {
            type: "single",
            data: {
                deletedCount: deletedIds.length,
                agentIds: deletedIds,
            },
            schema: deleteSchema,
        };
    }
    catch (err) {
        await client.close().catch(() => { });
        if (err && typeof err === "object" && "code" in err) {
            throw err;
        }
        const message = err instanceof Error ? err.message : String(err);
        const error = {
            code: "DELETE_AGENT_FAILED",
            message: `Failed to delete agent(s): ${message}`,
        };
        throw error;
    }
}
//# sourceMappingURL=delete.js.map