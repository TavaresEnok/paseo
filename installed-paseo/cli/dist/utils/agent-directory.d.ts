import type { AgentSnapshotPayload } from "@getpaseo/protocol/messages";
import type { connectToDaemon } from "./client.js";
type FetchAgentsOptions = NonNullable<Parameters<Awaited<ReturnType<typeof connectToDaemon>>["fetchAgents"]>[0]>;
interface AgentDirectoryClient {
    fetchAgents(options?: FetchAgentsOptions): Promise<{
        entries: {
            agent: AgentSnapshotPayload;
        }[];
        pageInfo: {
            nextCursor: string | null;
        };
    }>;
}
/** Read the complete directory without agents moving between pages as they update. */
export declare function fetchAllAgents(client: AgentDirectoryClient, options?: Omit<FetchAgentsOptions, "page" | "sort" | "subscribe">): Promise<AgentSnapshotPayload[]>;
export {};
//# sourceMappingURL=agent-directory.d.ts.map