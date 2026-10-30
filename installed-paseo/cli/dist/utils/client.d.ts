import { type DaemonInstance } from "@getpaseo/server/daemon-control";
import { type DaemonTarget } from "./daemon-target.js";
export type { DaemonTarget } from "./daemon-target.js";
import { DaemonClient } from "@getpaseo/client/internal/daemon-client";
export interface ConnectOptions {
    target: DaemonTarget;
    timeout?: number;
    instance?: DaemonInstance;
}
export declare function resolveClientPaseoHome(target: DaemonTarget, env?: Readonly<Record<string, string | undefined>>): string;
type TransportTarget = {
    type: "tcp";
    url: string;
} | {
    type: "ipc";
    url: string;
    socketPath: string;
};
export declare function getDaemonHost(options: ConnectOptions): string;
export declare function buildDaemonConnectionCommandError(options: ConnectOptions & {
    error: unknown;
}): {
    code: string;
    message: string;
    details: string;
};
export declare function normalizeDaemonHost(raw: string): string | null;
export declare function resolveDaemonTarget(host: string): TransportTarget;
export declare function resolveDaemonPassword(host: string): string | undefined;
export declare function resolveDaemonCredential(host: string, home: string): {
    kind: "password";
    password: string;
} | {
    kind: "localCredential";
    token: string;
} | null;
export declare function connectToDaemon(options: ConnectOptions): Promise<DaemonClient>;
/**
 * Try to connect to the daemon, returns null if connection fails
 */
export declare function tryConnectToDaemon(options: ConnectOptions): Promise<DaemonClient | null>;
/** Minimal agent type for ID resolution */
interface AgentLike {
    id: string;
    title?: string | null;
}
/**
 * Resolve an agent ID from a partial ID or name.
 * Supports:
 * - Full ID match
 * - Prefix match (first N characters)
 * - Title/name match (case-insensitive)
 *
 * Returns the full agent ID if found, null otherwise.
 */
export declare function resolveAgentId(idOrName: string, agents: AgentLike[]): string | null;
//# sourceMappingURL=client.d.ts.map