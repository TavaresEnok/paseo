import type { SessionDelivery } from "../session/owned-subscriptions/index.js";
import { EventEmitter } from "node:events";
import { type HostRouteFrame } from "@getpaseo/protocol/binary-frames/index";
import type { DaemonPermission, SessionInboundMessage } from "@getpaseo/protocol/messages";
/** A logical socket has no network resources or authority of its own. */
export declare class VirtualHostSocket extends EventEmitter {
    private readonly output;
    private readonly ended;
    private readonly buffered;
    private readonly transformHello;
    readyState: number;
    constructor(output: (data: string | Uint8Array) => Promise<void>, ended: (code: number, reason: string) => void, buffered: () => number, transformHello: (data: string) => string);
    get bufferedAmount(): number;
    private helloPending;
    feed(data: string | Uint8Array): void;
    send(data: string | Uint8Array | ArrayBuffer): Promise<void>;
    close(code?: number, reason?: string): void;
}
/** One authenticated physical source owns all its channels and their admission ceiling. */
export declare class DaemonLinkEndpoint {
    private readonly parent;
    private readonly channels;
    private closed;
    constructor(parent: {
        identity: string;
        permissions(): readonly DaemonPermission[];
        routed(): boolean;
        bufferedAmount(): number | null;
        delivery: SessionDelivery;
        admit(socket: VirtualHostSocket, permissions: readonly DaemonPermission[]): Promise<void>;
    });
    handles(message: SessionInboundMessage): boolean;
    dispatch(message: SessionInboundMessage): Promise<void>;
    binary(frame: HostRouteFrame): boolean;
    close(reason?: "host_offline" | "permission_denied"): void;
}
//# sourceMappingURL=link.d.ts.map