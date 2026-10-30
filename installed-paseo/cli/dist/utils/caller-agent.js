import { DaemonConnectionError } from "@getpaseo/client/internal/daemon-client";
// PASEO_AGENT_ID belongs to the daemon that launched this shell. Commands
// targeting another daemon (--host or --home) have no caller on that daemon.
export async function resolveCallerAgentId(client, env = process.env) {
    const agentId = env.PASEO_AGENT_ID?.trim();
    if (!agentId)
        return undefined;
    const caller = await client.fetchAgent({ agentId }).catch((error) => {
        // A missing agent is a daemon answer; a lost or timed-out connection is not.
        if (error instanceof DaemonConnectionError)
            throw error;
        return null;
    });
    return caller?.agent.id === agentId ? agentId : undefined;
}
//# sourceMappingURL=caller-agent.js.map