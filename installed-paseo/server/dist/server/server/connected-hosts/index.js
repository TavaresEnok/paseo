export { DaemonLinkEndpoint, VirtualHostSocket } from "./link.js";
export { ConnectedHostSession } from "./session.js";
import { randomUUID, createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { z } from "zod";
import { createHostClient, createHostChannelTransport, parseHostTarget, HostTransportBudget, } from "@getpaseo/client/node";
import { HostSummarySchema, HostAddSchema, HostUpdateSchema, } from "@getpaseo/protocol/hosts";
export class HostError extends Error {
    constructor(code, message, serverId) {
        super(message);
        this.code = code;
        this.serverId = serverId;
    }
}
const SavedSchema = HostSummarySchema.extend({ connection: z.string() });
/** Daemon-owned configuration, identity pinning, retry and routed session lifetime. */
export class ConnectedHosts {
    constructor(home, self) {
        this.home = home;
        this.self = self;
        this.budget = new HostTransportBudget();
        this.rows = [];
        this.live = new Map();
        this.routes = new Set();
        this.listeners = new Set();
        this.queue = Promise.resolve();
        this.closed = false;
        this.ready = this.load();
        void this.ready.catch(() => { });
    }
    async load() {
        try {
            this.rows = z
                .array(SavedSchema)
                .parse(JSON.parse(await readFile(join(this.home, "hosts.json"), "utf8")));
        }
        catch (error) {
            if (error.code !== "ENOENT")
                throw new Error("Cannot read saved connected hosts", { cause: error });
        }
        if (this.closed)
            return;
        for (const row of this.rows) {
            row.status = row.enabled ? "connecting" : "disabled";
            row.nextRetryAt = null;
            this.start(row);
        }
    }
    async list() {
        await this.ready;
        return {
            self: { ...this.self },
            hosts: this.rows.map(({ connection: _secret, ...row }) => structuredClone(row)),
        };
    }
    observe(changed) {
        this.listeners.add(changed);
        return () => this.listeners.delete(changed);
    }
    changed() {
        for (const listener of this.listeners)
            listener();
    }
    async persist(rows) {
        await mkdir(this.home, { recursive: true });
        const temp = join(this.home, `.hosts-${randomUUID()}.tmp`);
        try {
            await writeFile(temp, JSON.stringify(rows), { mode: 0o600 });
            await rename(temp, join(this.home, "hosts.json"));
        }
        finally {
            await rm(temp, { force: true });
        }
    }
    mutate(run) {
        const result = this.queue.then(async () => {
            await this.ready;
            if (this.closed)
                throw new HostError("host_offline", "Daemon is stopping");
            return run();
        });
        this.queue = result.catch(() => { });
        return result;
    }
    summary(row) {
        const { connection: _secret, ...summary } = row;
        return structuredClone(summary);
    }
    add(input, actor) {
        return this.mutate(async () => {
            input = HostAddSchema.parse(input);
            const target = parseHostTarget(input.connection);
            const source = { id: actor.sourceId, key: input.sourceKey ?? randomUUID() };
            const existing = this.rows.find((row) => row.source.id === source.id && row.source.key === source.key);
            if (existing) {
                if (existing.connection === input.connection &&
                    existing.label === (input.label ?? null) &&
                    JSON.stringify(Object.entries(existing.metadata).sort()) ===
                        JSON.stringify(Object.entries(input.metadata ?? {}).sort()))
                    return this.summary(existing);
                throw new HostError("source_conflict", "This source key already exists. Update its registration explicitly.");
            }
            if (this.rows.length >= 128)
                throw new HostError("resource_limit", "Remove a host before adding another (limit 128)");
            const row = {
                registrationId: `hst_${randomUUID()}`,
                serverId: null,
                connection: input.connection,
                label: input.label ?? null,
                metadata: input.metadata ?? {},
                source,
                enabled: true,
                status: "connecting",
                targetDescription: target.description,
                lastOnlineAt: null,
                nextRetryAt: null,
                error: null,
            };
            await this.persist([...this.rows, row]);
            this.rows.push(row);
            this.start(row);
            this.changed();
            return this.summary(row);
        });
    }
    update(id, patch, actor) {
        return this.mutate(async () => {
            patch = HostUpdateSchema.parse(patch);
            const previous = this.require(id);
            if ((patch.connection !== undefined || patch.metadata !== undefined || patch.replaceIdentity) &&
                actor.sourceId !== previous.source.id &&
                !actor.manageSources)
                throw new HostError("permission_denied", "Only the source or access manager can replace its connection and metadata");
            if (patch.replaceIdentity && patch.connection === undefined)
                throw new HostError("invalid_connection", "Identity replacement requires a replacement connection");
            const row = {
                ...previous,
                ...(patch.label !== undefined ? { label: patch.label } : {}),
                ...(patch.metadata !== undefined ? { metadata: patch.metadata } : {}),
                ...(patch.enabled !== undefined ? { enabled: patch.enabled } : {}),
            };
            if (patch.connection !== undefined) {
                row.connection = patch.connection;
                row.targetDescription = parseHostTarget(patch.connection).description;
            }
            if (patch.replaceIdentity)
                row.serverId = null;
            const restart = patch.connection !== undefined || patch.enabled !== undefined || patch.replaceIdentity;
            if (restart) {
                row.status = row.enabled ? "connecting" : "disabled";
                row.error = null;
                row.nextRetryAt = null;
            }
            const rows = this.rows.map((entry) => (entry === previous ? row : entry));
            await this.persist(rows);
            if (restart)
                this.stop(id, row.enabled ? "host_offline" : "host_disabled");
            Object.assign(previous, row);
            this.rows = rows.map((entry) => (entry === row ? previous : entry));
            if (restart)
                this.start(previous);
            this.changed();
            return this.summary(previous);
        });
    }
    remove(id, actor) {
        return this.mutate(async () => {
            const row = this.require(id);
            if (actor.sourceId !== row.source.id && !actor.manageSources)
                throw new HostError("permission_denied", "Only the source or access manager can remove this host. Disable it to stop access.");
            const rows = this.rows.filter((entry) => entry !== row);
            await this.persist(rows);
            this.stop(id, "host_unknown");
            this.rows = rows;
            this.changed();
        });
    }
    require(id) {
        const row = this.rows.find((entry) => entry.registrationId === id);
        if (!row)
            throw new HostError("host_unknown", "Unknown host registration");
        return row;
    }
    stop(id, code = "host_offline") {
        this.live.get(id)?.stop();
        this.live.delete(id);
        for (const route of this.routes)
            if (route.registrationId === id)
                route.close(code, "Host access was disabled, replaced or removed");
    }
    start(row) {
        if (!row.enabled || this.closed)
            return;
        let stopped = false;
        const client = createHostClient(row.connection, {
            clientId: `host-link-${this.self.serverId}-${row.registrationId}`,
            connectTimeoutMs: 10000,
        }, this.budget);
        const live = {
            client,
            accepted: false,
            stop: () => {
                stopped = true;
                void client.close();
            },
        };
        this.live.set(row.registrationId, live);
        const accept = async () => {
            try {
                const info = client.getLastServerInfoMessage();
                if (!info)
                    throw new HostError("host_offline", "No daemon identity received");
                if (row.serverId && info.serverId !== row.serverId)
                    throw new HostError("server_id_mismatch", "Daemon identity changed. Verify the destination and explicitly replace its identity.");
                if (!row.serverId)
                    await this.mutate(async () => {
                        if (stopped)
                            return;
                        const discovered = { ...row, serverId: info.serverId };
                        await this.persist(this.rows.map((entry) => (entry === row ? discovered : entry)));
                        row.serverId = info.serverId;
                    });
                if (info.serverId === this.self.serverId)
                    throw new HostError("self_host", "This connection reaches this daemon. Remove it or replace the connection.");
                if (this.rows.find((entry) => entry.serverId === info.serverId) !== row)
                    throw new HostError("duplicate_host", "Another registration already owns this daemon. Remove the duplicate registration.");
                if (info.features?.connectedHosts !== true || info.features?.hostMultiplexing !== true)
                    throw new HostError("unsupported_capability", "Update the destination daemon to use connected hosts.");
                // Pin and persist under the same writer as management to prevent discovery races.
                await this.mutate(async () => {
                    if (stopped)
                        return;
                    if (this.rows.find((entry) => entry.serverId === info.serverId) !== row)
                        throw new HostError("duplicate_host", "Another registration already owns this daemon");
                    const next = {
                        ...row,
                        serverId: info.serverId,
                        status: "online",
                        lastOnlineAt: new Date().toISOString(),
                        error: null,
                        nextRetryAt: null,
                    };
                    await this.persist(this.rows.map((entry) => (entry === row ? next : entry)));
                    if (stopped || client.getLastServerInfoMessage() !== info || !client.isConnected)
                        return;
                    Object.assign(row, next);
                    live.accepted = true;
                    this.changed();
                });
            }
            catch (error) {
                if (stopped)
                    return;
                row.status = "error";
                row.error = connectionFailure(error, client.authFailureReason !== null) ?? {
                    code: "host_offline",
                    message: "Host connection failed",
                };
                row.nextRetryAt = null;
                this.changed();
                await client.close();
            }
        };
        client.subscribeConnectionStatus((state) => {
            if (stopped || row.status === "error")
                return;
            live.accepted = false;
            if (state.status === "connected") {
                void accept();
                return;
            }
            for (const route of this.routes)
                if (route.registrationId === row.registrationId)
                    route.close();
            row.status = state.status === "connecting" ? "connecting" : "offline";
            row.nextRetryAt = state.status === "disconnected" ? (state.nextRetryAt ?? null) : null;
            row.error =
                state.status === "disconnected"
                    ? (connectionFailure(Object.assign(new Error("Check the SSH configuration and daemon credentials"), {
                        code: state.failureCode,
                    }), client.authFailureReason !== null) ?? {
                        code: "host_offline",
                        message: "Cannot reach host. Check the connection; retrying automatically.",
                    })
                    : null;
            if (row.error?.code === "authentication_failed") {
                row.status = "error";
                row.nextRetryAt = null;
                client.setReconnectEnabled(false);
                void client.close();
            }
            this.changed();
        });
        void client.connect().catch(() => { });
    }
    async openRoute(input) {
        await this.ready;
        const row = this.rows.find((entry) => entry.serverId === input.serverId);
        if (!row)
            throw new HostError("host_unknown", `Unknown host ${input.serverId}`, input.serverId);
        if (!row.enabled)
            throw new HostError("host_disabled", `Enable host ${input.serverId} before using it`, input.serverId);
        if (row.status !== "online")
            throw new HostError(row.error?.code ?? "host_offline", row.error?.message ?? `Host ${input.serverId} is offline`, input.serverId);
        if (this.routes.size >= 128)
            throw new HostError("resource_limit", "Too many routed sessions");
        const live = this.live.get(row.registrationId);
        const client = live?.client;
        if (!live?.accepted || !client?.isConnected)
            throw new HostError("host_offline", "Host is offline", input.serverId);
        const transport = createHostChannelTransport(client, input.serverId, randomUUID(), null, true)({ url: "ws://host-link/ws" });
        let closed = false;
        let verified = false;
        let helloSent = false;
        const timer = setTimeout(() => route.close("host_offline", "Host handshake timed out"), 15000);
        timer.unref();
        const route = {
            registrationId: row.registrationId,
            close: (code = "host_offline", message = `Host ${input.serverId} disconnected`) => {
                if (closed)
                    return;
                closed = true;
                input.signal.removeEventListener("abort", abort);
                clearTimeout(timer);
                this.routes.delete(route);
                try {
                    transport.close();
                }
                finally {
                    failed(new HostError(code, message, input.serverId));
                    input.ended(code, message);
                }
            },
        };
        this.routes.add(route);
        const abort = () => route.close("host_offline", "Origin session closed or its authority changed");
        input.signal.addEventListener("abort", abort, { once: true });
        let opened;
        let failed;
        const ready = new Promise((resolve, reject) => {
            opened = resolve;
            failed = reject;
        });
        if (input.signal.aborted) {
            route.close();
        }
        transport.onOpen(opened);
        transport.onError((error) => {
            const authenticationFailed = error instanceof Error && "code" in error && error.code === "authentication_failed";
            const code = authenticationFailed ? "authentication_failed" : "host_offline";
            const message = authenticationFailed
                ? "Host authentication failed. Check the SSH configuration and daemon credentials."
                : "Host transport failed";
            failed(new HostError(code, message, input.serverId));
            route.close(code, message);
        });
        transport.onClose(() => {
            failed(new HostError("host_offline", "Host transport closed"));
            route.close();
        });
        transport.onMessage((data, binary) => {
            if (closed)
                return;
            if (!verified) {
                if (binary) {
                    route.close();
                    return;
                }
                try {
                    const envelope = JSON.parse(String(data));
                    if (envelope.type === "hello.rejected") {
                        route.close("authentication_failed", "Replace the host credentials");
                        return;
                    }
                    const info = envelope.type === "session" && envelope.message.type === "status"
                        ? envelope.message.payload
                        : null;
                    if (info?.status !== "server_info")
                        return;
                    if (info.serverId !== row.serverId) {
                        route.close("server_id_mismatch", "Host identity changed; explicit replacement required");
                        return;
                    }
                    if (info.features?.connectedHosts !== true) {
                        route.close("unsupported_capability", "Update the destination daemon");
                        return;
                    }
                    verified = true;
                    clearTimeout(timer);
                }
                catch {
                    route.close();
                    return;
                }
            }
            input.frame(binary ? data : String(data));
        });
        await ready;
        if (closed)
            throw new HostError("host_offline", "Host closed during connection");
        return {
            close: () => route.close(),
            send: (data) => {
                const binary = typeof data !== "string";
                if (closed)
                    throw new HostError("host_offline", "Host is offline");
                if (!helloSent) {
                    if (binary)
                        throw new HostError("invalid_message", "Expected hello");
                    const hello = JSON.parse(data);
                    if (hello.type !== "hello")
                        throw new HostError("invalid_message", "Expected hello");
                    const clientId = `route-${createHash("sha256")
                        .update(JSON.stringify([
                        this.self.serverId,
                        input.sourceId,
                        input.originSessionId,
                        input.scopeId,
                    ]))
                        .digest("hex")}`;
                    transport.send(JSON.stringify({
                        ...hello,
                        clientId,
                        routed: true,
                        producer: { serverId: this.self.serverId, sourceId: input.sourceId },
                        sessionPermissions: input.permissions,
                        auth: undefined,
                    }));
                    helloSent = true;
                    return;
                }
                if (!verified)
                    throw new HostError("host_offline", "Host identity has not been verified");
                try {
                    transport.send(data);
                }
                catch {
                    route.close("resource_limit", "Host buffer limit reached or transport unavailable");
                }
            },
        };
    }
    async close() {
        this.closed = true;
        await this.ready;
        await this.queue;
        for (const id of this.live.keys())
            this.stop(id);
        for (const route of this.routes)
            route.close();
        this.listeners.clear();
    }
}
function connectionFailure(error, authenticationFailed) {
    if (error instanceof HostError)
        return { code: error.code, message: error.message };
    if (error instanceof Error && "code" in error && error.code === "authentication_failed")
        return { code: "authentication_failed", message: error.message };
    if (authenticationFailed)
        return {
            code: "authentication_failed",
            message: "Host rejected the credentials. Replace the connection credentials.",
        };
    return null;
}
//# sourceMappingURL=index.js.map