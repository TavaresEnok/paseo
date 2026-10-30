import { Command } from "commander";
import { connectToDaemon } from "../../utils/client.js";
import type { CommandOptions, SingleResult, OutputSchema } from "../../output/index.js";
export { resolveProviderAndModel } from "../../utils/provider-model.js";
export declare function addRunOptions(cmd: Command): Command;
/** Result type for agent run command */
export interface AgentRunResult {
    agentId: string;
    status: "created" | "running" | "completed" | "timeout" | "permission" | "error";
    provider: string;
    cwd: string;
    title: string | null;
}
/** Schema for agent run output */
export declare const agentRunSchema: OutputSchema<AgentRunResult>;
export interface AgentRunOptions extends CommandOptions {
    wait?: boolean;
    background?: boolean;
    detach?: boolean;
    title?: string;
    name?: string;
    provider?: string;
    model?: string;
    thinking?: string;
    mode?: string;
    newWorkspace?: string;
    worktree?: string;
    worktreeMode?: string;
    worktreeSlug?: string;
    newBranch?: string;
    base?: string;
    branch?: string;
    prNumber?: string;
    forge?: string;
    workspace?: string;
    image?: string[];
    cwd?: string;
    env?: string[];
    label?: string[];
    waitTimeout?: string;
    outputSchema?: string;
}
type ConnectedDaemonClient = Awaited<ReturnType<typeof connectToDaemon>>;
export interface StructuredResponseTimelineClient {
    fetchAgentTimeline: ConnectedDaemonClient["fetchAgentTimeline"];
}
export declare function resolveStructuredResponseMessage(options: {
    client: StructuredResponseTimelineClient;
    agentId: string;
    lastMessage: string | null;
}): Promise<string | null>;
export declare function waitsForFinish(options: Pick<AgentRunOptions, "wait" | "background" | "detach">): boolean;
interface RunWorkspace {
    id?: string;
    cwd: string;
}
export interface RunWorkspaceLookupClient {
    fetchWorkspaces(options: {
        filter: {
            query: string;
        };
        page: {
            limit: number;
        };
    }): Promise<{
        entries: Array<{
            id: string;
            workspaceDirectory: string;
        }>;
        pageInfo: {
            nextCursor: string | null;
        };
    }>;
}
export declare function resolveExistingRunWorkspace(client: RunWorkspaceLookupClient, workspaceId: string): Promise<RunWorkspace>;
export declare function runRunCommand(prompt: string, options: AgentRunOptions, _command: Command): Promise<SingleResult<AgentRunResult>>;
//# sourceMappingURL=run.d.ts.map