import { type HostRouteFrame } from "@getpaseo/protocol/binary-frames/index";
import type { SessionInboundMessage, SessionOutboundMessage, DaemonPermission } from "@getpaseo/protocol/messages";
import { ConnectedHosts, type HostActor } from "./index.js";
import type { SessionDelivery } from "../session/owned-subscriptions/index.js";
/** Adapts host capabilities to source-owned session delivery. */
export declare class ConnectedHostSession {
    private readonly hosts;
    private readonly delivery;
    private readonly actor;
    private readonly permissions;
    private readonly emit;
    private readonly routed;
    private readonly originSessionId;
    private readonly bufferedAmount;
    private readonly routes;
    constructor(hosts: ConnectedHosts, delivery: SessionDelivery, actor: HostActor, permissions: () => DaemonPermission[], emit: (message: SessionOutboundMessage) => void, routed: () => boolean, originSessionId: string, bufferedAmount: (source: object) => number | null);
    binary(frame: HostRouteFrame, source: object): void;
    setSource(sourceId: string): void;
    dispatch(message: SessionInboundMessage): Promise<void> | undefined;
    revoke(): void;
    private handle;
    private fail;
    private execute;
    private list;
    private open;
}
//# sourceMappingURL=session.d.ts.map