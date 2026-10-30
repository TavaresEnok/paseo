import { createObservationBuffer } from "./observation-buffer.js";
function isTerminal(snapshot, event) {
    if (snapshot.status === "closed" || snapshot.status === "error")
        return true;
    return (snapshot.status === "idle" &&
        (event?.type === "turn_completed" || event?.type === "turn_canceled"));
}
function observeState(buffer, snapshot, event, lastMessage = null) {
    if (!snapshot) {
        buffer.push({ status: "idle", final: null, lastMessage: null, error: null });
        return;
    }
    if (event?.type === "permission_resolved") {
        buffer.resolved(event.requestId);
        return;
    }
    if (event?.type === "turn_started")
        return;
    if (event?.type === "permission_requested") {
        buffer.push({
            status: "permission",
            final: { ...snapshot, pendingPermissions: [event.request] },
            lastMessage,
            error: null,
        });
    }
    else if (isTerminal(snapshot, event)) {
        buffer.push({
            status: snapshot.status === "error" ? "error" : "idle",
            final: snapshot,
            lastMessage,
            error: snapshot.lastError ?? null,
            ...(event?.type === "turn_canceled" ? { reason: "was canceled" } : {}),
        });
    }
}
/** One continuous source feeds a bounded buffer while the caller awaits dispatch. */
export async function openFinishObservation(resolver, record, signal) {
    signal.throwIfAborted();
    const controller = new AbortController();
    const lifetime = AbortSignal.any([signal, controller.signal]);
    const buffer = createObservationBuffer(lifetime);
    let opened;
    let failed;
    const ready = new Promise((resolve, reject) => {
        opened = resolve;
        failed = reject;
    });
    const route = resolver
        .use(record.serverId, async (host) => {
        const release = await host.observe(record.childAgentId, (snapshot, event, lastMessage) => observeState(buffer, snapshot, event, lastMessage), lifetime, (error) => buffer.fail(error));
        opened();
        // The ordinary wait supplies the initial settled snapshot and covers queued admission.
        // Continuous observation buffers checkpoints and terminal events throughout delivery.
        void host
            .wait(record.childAgentId, lifetime)
            .then((result) => {
            buffer.pushInitial(result);
            return undefined;
        })
            .catch((error) => buffer.fail(error));
        try {
            if (!lifetime.aborted)
                await new Promise((resolve) => lifetime.addEventListener("abort", () => resolve(), { once: true }));
        }
        finally {
            await release();
        }
    }, lifetime)
        .catch((error) => {
        failed(error);
        buffer.fail(error);
    });
    try {
        await ready;
    }
    catch (error) {
        controller.abort();
        buffer.dispose();
        await route;
        throw error;
    }
    return {
        next: () => buffer.next(),
        async close() {
            controller.abort();
            buffer.dispose();
            await route;
        },
    };
}
//# sourceMappingURL=observation-stream.js.map