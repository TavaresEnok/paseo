interface CallerLookupClient {
    fetchAgent(options: {
        agentId: string;
    }): Promise<{
        agent: {
            id: string;
        };
    } | null>;
}
export declare function resolveCallerAgentId(client: CallerLookupClient, env?: {
    PASEO_AGENT_ID?: string;
}): Promise<string | undefined>;
export {};
//# sourceMappingURL=caller-agent.d.ts.map