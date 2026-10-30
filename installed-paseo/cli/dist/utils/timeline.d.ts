import type { DaemonClient } from "@getpaseo/client/internal/daemon-client";
import type { AgentTimelineItem } from "@getpaseo/protocol/agent-types";
export declare const LIVE_HISTORY_FETCH_TIMEOUT_MS = 2000;
interface FetchProjectedTimelineItemsInput {
    client: DaemonClient;
    agentId: string;
    timeoutMs?: number;
    sinceTimestampMs?: number;
}
export declare function fetchProjectedTimelineItems(input: FetchProjectedTimelineItemsInput): Promise<AgentTimelineItem[]>;
export {};
//# sourceMappingURL=timeline.d.ts.map