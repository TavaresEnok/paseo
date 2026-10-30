import { EventEmitter } from "node:events";
import { createHash } from "node:crypto";
import { encodeHostRouteFrame } from "@getpaseo/protocol/binary-frames/index";
/** A logical socket has no network resources or authority of its own. */
export class VirtualHostSocket extends EventEmitter {
    constructor(output, ended, buffered, transformHello) {
        super();
        this.output = output;
        this.ended = ended;
        this.buffered = buffered;
        this.transformHello = transformHello;
        this.readyState = 1;
        this.helloPending = true;
    }
    get bufferedAmount() {
        return this.buffered();
    }
    feed(data) {
        if (this.readyState !== 1)
            return;
        if (this.helloPending) {
            if (typeof data !== "string") {
                this.close(1008, "Expected hello");
                return;
            }
            try {
                data = this.transformHello(data);
            }
            catch {
                this.close(1008, "Invalid hello");
                return;
            }
            this.helloPending = false;
        }
        this.emit("message", typeof data === "string" ? data : Buffer.from(data));
    }
    async send(data) {
        if (this.readyState !== 1)
            throw new Error("Host channel closed");
        await this.output(typeof data === "string" || data instanceof Uint8Array ? data : new Uint8Array(data));
    }
    close(code = 1000, reason = "Host channel closed") {
        if (this.readyState !== 1)
            return;
        this.readyState = 3;
        this.ended(code, reason);
        this.emit("close", 1000, "Host channel closed");
    }
}
/** One authenticated physical source owns all its channels and their admission ceiling. */
export class DaemonLinkEndpoint {
    constructor(parent) {
        this.parent = parent;
        this.channels = new Map();
        this.closed = false;
    }
    handles(message) {
        return (message.type === "hosts.link.open.request" ||
            (message.type === "hosts.route.frame.request" && this.channels.has(message.routeId)) ||
            (message.type === "hosts.route.close.request" &&
                ((!!message.routeId && this.channels.has(message.routeId)) ||
                    [...this.channels.values()].some((channel) => channel.scopeId === message.scopeId))));
    }
    async dispatch(message) {
        if (message.type === "hosts.link.open.request") {
            const error = (code, text) => this.parent.delivery.reply({
                type: "rpc_error",
                payload: {
                    requestId: message.requestId,
                    requestType: message.type,
                    code,
                    error: text,
                },
            });
            if (this.closed || this.parent.routed()) {
                error("unsupported_capability", "Connected hosts support one hop");
                return;
            }
            if (this.channels.size >= 128) {
                error("resource_limit", "Too many host channels");
                return;
            }
            let socket;
            const owner = this.parent.delivery.begin("host-link", undefined, () => {
                this.channels.delete(owner.id);
                socket?.close();
            });
            const id = owner.id;
            // Capture actual authenticated authority. The caller hello can only reduce it.
            const ceiling = [...this.parent.permissions()];
            socket = new VirtualHostSocket(async (data) => {
                const output = typeof data === "string"
                    ? {
                        type: "hosts.route.frame",
                        payload: { subscriptionId: id, data, binary: false },
                    }
                    : null;
                const frame = typeof data === "string" ? null : encodeHostRouteFrame(id, data);
                const bytes = output
                    ? Buffer.byteLength(JSON.stringify({ type: "session", message: output }))
                    : frame.byteLength;
                const buffered = this.parent.bufferedAmount();
                // Account for the exact escaped outer frame, retaining control-frame headroom.
                if (buffered === null || buffered + bytes > 64 * 1024 * 1024 - 65536) {
                    socket.close(1009, "Host channel output limit reached");
                    throw new Error("Host channel output limit reached");
                }
                try {
                    if (output)
                        await owner.emitAndWait(output);
                    else
                        await owner.emitBinaryAndWait(frame);
                }
                catch (failure) {
                    socket.close();
                    throw failure;
                }
            }, (code, reason) => {
                this.channels.delete(id);
                let failure = "host_offline";
                if (code === 1009)
                    failure = "resource_limit";
                if (code === 1008)
                    failure = "permission_denied";
                owner.emit({
                    type: "hosts.route.closed",
                    payload: {
                        subscriptionId: id,
                        code: failure,
                        message: reason,
                    },
                });
                void owner.release();
            }, () => this.parent.bufferedAmount() ?? 0, (data) => {
                const hello = JSON.parse(data);
                if (hello.type !== "hello" || typeof hello.clientId !== "string")
                    throw new Error("Expected hello");
                return JSON.stringify({
                    ...hello,
                    auth: undefined,
                    routed: true,
                    clientId: `link-${createHash("sha256")
                        .update(JSON.stringify([this.parent.identity, hello.clientId]))
                        .digest("hex")}`,
                });
            });
            this.channels.set(id, { scopeId: message.channelId, socket });
            try {
                await this.parent.admit(socket, ceiling);
                if (this.closed || socket.readyState !== 1) {
                    socket.close();
                    return;
                }
                this.parent.delivery.reply({
                    type: "hosts.link.open.response",
                    payload: { requestId: message.requestId, routeId: id },
                });
            }
            catch {
                socket.close();
                error("host_offline", "Could not admit host channel");
            }
            return;
        }
        if (message.type === "hosts.route.frame.request" && this.channels.has(message.routeId)) {
            this.channels.get(message.routeId).socket.feed(message.data);
            return;
        }
        if (message.type === "hosts.route.close.request") {
            for (const [id, channel] of this.channels) {
                if (message.routeId === id || (message.scopeId && message.scopeId === channel.scopeId))
                    channel.socket.close();
            }
        }
        return;
    }
    binary(frame) {
        const socket = this.channels.get(frame.routeId)?.socket;
        if (!socket)
            return false;
        socket.feed(frame.payload);
        return true;
    }
    close(reason = "host_offline") {
        if (this.closed)
            return;
        this.closed = true;
        for (const { socket } of this.channels.values())
            socket.close(reason === "permission_denied" ? 1008 : 1000, "Physical link authority or connection changed");
        this.channels.clear();
    }
}
//# sourceMappingURL=link.js.map