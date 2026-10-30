import type { AgentStreamEvent } from "../agent-sdk-types.js";
import type { AgentSnapshotPayload } from "@getpaseo/protocol/messages";
import { DaemonClient, type WaitForFinishResult } from "@getpaseo/client/internal/daemon-client";
import type { HostDirectory } from "@getpaseo/protocol/hosts";
import type { ConnectedHosts } from "../../connected-hosts/index.js";
import type { PaseoToolExecutionContext, PaseoToolResult } from "../tools/types.js";
export declare class HostOperationRejectedError extends Error {
    readonly code: unknown;
    constructor(error: unknown);
}
export type HostOperation = (input: Record<string, unknown>, context: PaseoToolExecutionContext) => Promise<PaseoToolResult>;
export interface HostOperations {
    createAgent: HostOperation;
    createWorkspace: HostOperation;
    listWorkspaces: HostOperation;
    sendPrompt: HostOperation;
    getStatus: HostOperation;
    getActivity: HostOperation;
    listAgents: HostOperation;
}
/** Connection authority at the host boundary, independent of child lifecycle. */
export declare class HostObservationError extends Error {
    readonly reason: "connecting" | "unreachable" | "removed";
    constructor(reason: "connecting" | "unreachable" | "removed", cause?: unknown);
}
export interface HostObservation {
    wait(agentId: string, signal: AbortSignal): Promise<WaitForFinishResult>;
    observe(agentId: string, handler: (snapshot: AgentSnapshotPayload | null, event?: AgentStreamEvent, lastMessage?: string | null) => void, signal: AbortSignal, onError: (error: unknown) => void): Promise<() => Promise<void>>;
}
export interface ToolHosts {
    directory(): Promise<HostDirectory>;
    use<T>(serverId: string, action: (client: DaemonClient) => Promise<T>, signal?: AbortSignal): Promise<T>;
}
/** Daemon MCP has the daemon's authority, bounded by the destination's admission of its link. */
export declare function createToolHosts(hosts: ConnectedHosts): ToolHosts;
export declare function createHostResolver(input: {
    serverId: string;
    local: HostOperations;
    hosts: () => ToolHosts;
    callerAgentId?: string;
    lockedCwd?: string;
}): {
    directory: () => Promise<{
        self: {
            serverId: string;
            label: string;
        };
        hosts: {
            registrationId: string;
            serverId: string | null;
            label: string | null;
            source: {
                id: string;
                key: string;
            };
            metadata: Record<string, string>;
            enabled: boolean;
            status: "error" | "connecting" | "online" | "offline" | "disabled";
            targetDescription: string;
            lastOnlineAt: string | null;
            nextRetryAt: string | null;
            error: {
                code: string;
                message: string;
            } | null;
        }[];
    }>;
    use<T>(serverId: string | undefined, action: (host: HostOperations) => Promise<T>): Promise<T>;
};
/** Shares routed status observation with daemon services independently of MCP execution. */
export declare function createHostObservationResolver(input: {
    serverId: string;
    local: HostObservation;
    hosts(): ToolHosts;
}): {
    use<T>(serverId: string | undefined, action: (host: HostObservation) => Promise<T>, signal?: AbortSignal): Promise<T>;
};
//# sourceMappingURL=index.d.ts.map