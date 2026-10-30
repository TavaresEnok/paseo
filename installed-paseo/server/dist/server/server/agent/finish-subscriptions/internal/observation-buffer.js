/** Coalesces duplicate checkpoints and retains one terminal result while delivery is pending. */
export function createObservationBuffer(signal) {
    const delivered = new Set();
    const permissions = new Map();
    const resolvedBeforeInitial = new Set();
    let initialPending = true;
    let terminal;
    let failure;
    let wake;
    const abort = () => {
        failure = signal.reason;
        wake?.();
    };
    signal.addEventListener("abort", abort, { once: true });
    function push(result) {
        if (result.status === "timeout")
            return;
        if (result.status === "permission") {
            for (const request of result.final?.pendingPermissions ?? [])
                if (!delivered.has(request.id))
                    permissions.set(request.id, result);
        }
        else
            terminal = result;
        wake?.();
    }
    return {
        pushInitial(result) {
            initialPending = false;
            if (result.status === "permission" && result.final) {
                const pendingPermissions = result.final.pendingPermissions.filter((request) => !resolvedBeforeInitial.has(request.id));
                if (pendingPermissions.length)
                    push({ ...result, final: { ...result.final, pendingPermissions } });
            }
            else if (!terminal &&
                result.final?.status !== "running" &&
                result.final?.status !== "initializing")
                push(result);
            resolvedBeforeInitial.clear();
        },
        push,
        resolved(id) {
            if (initialPending)
                resolvedBeforeInitial.add(id);
            delivered.delete(id);
            permissions.delete(id);
        },
        fail(error) {
            failure = error;
            wake?.();
        },
        async next() {
            while (true) {
                signal.throwIfAborted();
                const first = permissions.entries().next().value;
                if (first) {
                    for (const request of first[1].final?.pendingPermissions ?? []) {
                        delivered.add(request.id);
                        permissions.delete(request.id);
                    }
                    return first[1];
                }
                if (terminal) {
                    const result = terminal;
                    terminal = undefined;
                    return result;
                }
                if (failure)
                    throw failure;
                await new Promise((resolve) => {
                    wake = resolve;
                });
                wake = undefined;
            }
        },
        dispose() {
            signal.removeEventListener("abort", abort);
        },
    };
}
//# sourceMappingURL=observation-buffer.js.map