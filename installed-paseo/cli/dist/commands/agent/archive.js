import { connectToDaemon, resolveAgentId } from "../../utils/client.js";
import { fetchAllAgents } from "../../utils/agent-directory.js";
/** Schema for archive command output */
export const archiveSchema = {
    idField: "agentId",
    columns: [
        { header: "AGENT ID", field: "agentId" },
        { header: "STATUS", field: "status" },
        { header: "ARCHIVED AT", field: "archivedAt" },
    ],
};
export function addArchiveOptions(cmd) {
    return cmd
        .description("Archive an agent (soft-delete)")
        .argument("<id>", "Agent ID, prefix, or name")
        .option("--force", "Force archive running agent (interrupts active run first)");
}
export async function runArchiveCommand(agentIdArg, options, _command) {
    // Validate arguments
    if (!agentIdArg || agentIdArg.trim().length === 0) {
        const error = {
            code: "MISSING_AGENT_ID",
            message: "Agent ID is required",
            details: "Usage: paseo agent archive <id-or-name>",
        };
        throw error;
    }
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const agents = await fetchAllAgents(client, { filter: { includeArchived: true } });
        const agentId = resolveAgentId(agentIdArg, agents);
        if (!agentId) {
            const error = {
                code: "AGENT_NOT_FOUND",
                message: `Agent not found: ${agentIdArg}`,
                details: 'Use "paseo ls" to list available agents',
            };
            throw error;
        }
        const agent = agents.find((entry) => entry.id === agentId);
        if (!agent) {
            throw new Error(`Resolved agent missing from fetched agents: ${agentId}`);
        }
        // Check if agent is already archived
        if (agent.archivedAt) {
            const error = {
                code: "AGENT_ALREADY_ARCHIVED",
                message: `Agent ${agentId.slice(0, 7)} is already archived`,
                details: `Archived at: ${agent.archivedAt}`,
            };
            throw error;
        }
        // Check if agent is running and reject unless --force is set
        if (agent.status === "running" && !options.force) {
            const error = {
                code: "AGENT_RUNNING",
                message: `Agent ${agentId.slice(0, 7)} is currently running`,
                details: "Use --force to archive a running agent (it will interrupt the active run), or stop it first with: paseo agent stop. Use paseo agent delete to hard-delete it.",
            };
            throw error;
        }
        // Archive the agent
        const result = await client.archiveAgent(agentId);
        await client.close();
        return {
            type: "single",
            data: {
                agentId,
                status: "archived",
                archivedAt: result.archivedAt,
            },
            schema: archiveSchema,
        };
    }
    catch (err) {
        await client.close().catch(() => { });
        // Re-throw CommandError as-is
        if (err && typeof err === "object" && "code" in err) {
            throw err;
        }
        const message = err instanceof Error ? err.message : String(err);
        const error = {
            code: "ARCHIVE_FAILED",
            message: `Failed to archive agent: ${message}`,
        };
        throw error;
    }
}
//# sourceMappingURL=archive.js.map