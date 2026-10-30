/** Read the complete directory without agents moving between pages as they update. */
export async function fetchAllAgents(client, options = {}) {
    const agents = [];
    let cursor;
    // createdAt never changes, so agents cannot move past the cursor while the pages are read.
    do {
        const payload = await client.fetchAgents({
            ...options,
            sort: [{ key: "created_at", direction: "desc" }],
            page: { limit: 200, ...(cursor ? { cursor } : {}) },
        });
        agents.push(...payload.entries.map((entry) => entry.agent));
        cursor = payload.pageInfo.nextCursor ?? undefined;
    } while (cursor);
    return agents;
}
//# sourceMappingURL=agent-directory.js.map