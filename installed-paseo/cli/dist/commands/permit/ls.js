import { connectToDaemon } from "../../utils/client.js";
/** Schema for permit ls output */
export const permitLsSchema = {
    idField: "id",
    columns: [
        { header: "AGENT", field: "agentShortId", width: 12 },
        { header: "REQ_ID", field: (item) => item.id.slice(0, 8), width: 12 },
        { header: "TOOL", field: "name", width: 20 },
        { header: "DESCRIPTION", field: "description", width: 50 },
    ],
};
/** Transform agent snapshot + permission to list item */
function toListItem(agent, permission) {
    return {
        id: permission.id,
        agentId: agent.id,
        agentShortId: agent.id.slice(0, 7),
        name: permission.name,
        description: permission.description ?? "-",
    };
}
/** Collect the pending permissions of every agent */
export function listPendingPermissions(agents) {
    const items = [];
    for (const agent of agents) {
        for (const permission of agent.pendingPermissions ?? []) {
            items.push(toListItem(agent, permission));
        }
    }
    return {
        type: "list",
        data: items,
        schema: permitLsSchema,
    };
}
export async function runLsCommand(options, _command) {
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const agentsPayload = await client.fetchAgents({ filter: { includeArchived: true } });
        const agents = agentsPayload.entries.map((entry) => entry.agent);
        await client.close();
        return listPendingPermissions(agents);
    }
    catch (err) {
        await client.close().catch(() => { });
        const message = err instanceof Error ? err.message : String(err);
        const error = {
            code: "LIST_PERMISSIONS_FAILED",
            message: `Failed to list permissions: ${message}`,
        };
        throw error;
    }
}
//# sourceMappingURL=ls.js.map