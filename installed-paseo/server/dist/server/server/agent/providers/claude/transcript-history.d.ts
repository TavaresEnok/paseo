import { type ClaudeReplayEntry, type ClaudeSubagentMeta } from "./subagents/replay-source.js";
import { type ClaudeWorkflowRun } from "./subagents/workflow-replay-source.js";
interface TranscriptEntry extends ClaudeReplayEntry {
    isSidechain?: unknown;
}
/** Discover sources without retaining transcript contents. Unrelated sidechains stay excluded
 * by the replay ownership resolver; workflow children retain their separate run ownership. */
export interface ClaudeReplayHistory {
    parentEntries: Iterable<TranscriptEntry>;
    subagents: {
        agentId: string;
        meta: ClaudeSubagentMeta | null;
        entries: Iterable<TranscriptEntry>;
    }[];
    workflows: ClaudeWorkflowRun[];
    workflowEntriesByRunId: Map<string, Iterable<TranscriptEntry>>;
}
/** Own descriptors through every pass so unlink or rename cannot invalidate discovered history.
 * Sources must be consumed before the callback returns. No transcript copies are needed. */
export declare function withClaudeReplayHistory<T>(historyPath: string, consume: (history: ClaudeReplayHistory) => T): T;
export {};
//# sourceMappingURL=transcript-history.d.ts.map