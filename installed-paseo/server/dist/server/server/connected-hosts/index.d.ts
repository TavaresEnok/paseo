export { DaemonLinkEndpoint, VirtualHostSocket } from "./link.js";
export { ConnectedHostSession } from "./session.js";
import { type HostDirectory, type HostSummary, type HostAdd, type HostUpdate } from "@getpaseo/protocol/hosts";
import type { DaemonPermission } from "@getpaseo/protocol/messages";
export declare class HostError extends Error {
    readonly code: string;
    readonly serverId?: string | undefined;
    constructor(code: string, message: string, serverId?: string | undefined);
}
export interface HostActor {
    sourceId: string;
    manageSources: boolean;
}
/** Daemon-owned configuration, identity pinning, retry and routed session lifetime. */
export declare class ConnectedHosts {
    private readonly home;
    private readonly self;
    private readonly budget;
    private rows;
    private readonly live;
    private readonly routes;
    private readonly listeners;
    private queue;
    private readonly ready;
    private closed;
    constructor(home: string, self: HostDirectory["self"]);
    private load;
    list(): Promise<HostDirectory>;
    observe(changed: () => void): () => void;
    private changed;
    private persist;
    private mutate;
    private summary;
    add(input: HostAdd, actor: HostActor): Promise<HostSummary>;
    update(id: string, patch: HostUpdate, actor: HostActor): Promise<HostSummary>;
    remove(id: string, actor: HostActor): Promise<void>;
    private require;
    private stop;
    private start;
    openRoute(input: {
        serverId: string;
        scopeId: string;
        sourceId: string;
        originSessionId: string;
        permissions: readonly DaemonPermission[];
        signal: AbortSignal;
        frame(data: string | Uint8Array): void;
        ended(code: string, message: string): void;
    }): Promise<{
        send(data: string | Uint8Array): void;
        close(): void;
    }>;
    close(): Promise<void>;
}
//# sourceMappingURL=index.d.ts.map