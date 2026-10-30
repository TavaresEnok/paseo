export const LIVE_HISTORY_FETCH_TIMEOUT_MS = 2000;
export async function fetchProjectedTimelineItems(input) {
    const timeline = await input.client.fetchAgentTimeline(input.agentId, {
        direction: "tail",
        limit: 0,
        projection: "projected",
        timeout: input.timeoutMs,
    });
    let entries = timeline.entries;
    const sinceTimestampMs = input.sinceTimestampMs;
    if (sinceTimestampMs !== undefined) {
        entries = entries.filter((entry) => Date.parse(entry.timestamp) >= sinceTimestampMs);
    }
    return entries.map((entry) => entry.item);
}
//# sourceMappingURL=timeline.js.map