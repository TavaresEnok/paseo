import { Command } from "commander";
import type { CommandOptions } from "../../output/index.js";
import type { DaemonClient } from "@getpaseo/client/internal/daemon-client";
import type { AgentTimelineItem } from "@getpaseo/protocol/agent-types";
export declare function addLogsOptions(cmd: Command): Command;
export interface AgentLogsOptions extends CommandOptions {
    follow?: boolean;
    tail?: string;
    filter?: string;
    since?: string;
}
export type AgentLogsResult = void;
export declare const NO_ACTIVITY_MESSAGE = "No activity to display.";
interface FetchAgentTimelineItemsOptions {
    timeoutMs?: number;
    sinceTimestampMs?: number;
}
export declare function fetchAgentTimelineItems(client: DaemonClient, agentId: string, options?: FetchAgentTimelineItemsOptions): Promise<AgentTimelineItem[]>;
export declare function formatAgentActivityTranscript(timelineItems: AgentTimelineItem[], tailCount?: number): string;
export interface FollowTranscriptWriter {
    push(item: AgentTimelineItem, turnId?: string): void;
    end(): void;
}
/**
 * Follow mode receives one streaming fragment per event, while the one-shot
 * transcript sees the whole timeline and merges consecutive assistant and
 * reasoning fragments with exact concatenation (`projectTimelineRows`). Printing
 * each fragment on its own line splits words at fragment boundaries and
 * reprints the reasoning prefix, so a chain of fragments is written as one
 * stream instead: text goes out as it arrives, and only the trailing whitespace
 * is held back so the message ends trimmed the way the transcript does.
 */
export declare function createFollowTranscriptWriter(write?: (chunk: string) => void, filter?: string): FollowTranscriptWriter;
export declare function runLogsCommand(id: string, options: AgentLogsOptions, _command: Command): Promise<AgentLogsResult>;
export {};
//# sourceMappingURL=logs.d.ts.map