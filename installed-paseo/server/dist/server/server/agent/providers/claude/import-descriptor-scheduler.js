import pLimit from "p-limit";
export function createImportDescriptorScheduler(read) {
    const limit = pLimit(4);
    const reads = new Map();
    function acquire(candidate) {
        let pending = reads.get(candidate.cacheKey);
        if (!pending) {
            const controller = new AbortController();
            const entry = {
                controller,
                subscribers: 0,
                settled: false,
                promise: limit(() => {
                    controller.signal.throwIfAborted();
                    return read(candidate, controller.signal);
                }).finally(() => {
                    entry.settled = true;
                    if (reads.get(candidate.cacheKey) === entry)
                        reads.delete(candidate.cacheKey);
                }),
            };
            reads.set(candidate.cacheKey, entry);
            pending = entry;
        }
        pending.subscribers += 1;
        return pending;
    }
    function release(candidate, pending) {
        pending.subscribers -= 1;
        // The initiating listing has no special ownership of a shared read.
        if (pending.subscribers === 0 && !pending.settled) {
            if (reads.get(candidate.cacheKey) === pending)
                reads.delete(candidate.cacheKey);
            pending.controller.abort();
        }
    }
    return async (candidates, signal) => {
        signal.throwIfAborted();
        const controller = new AbortController();
        signal = AbortSignal.any([signal, controller.signal]);
        let onAbort;
        const aborted = new Promise((_resolve, reject) => {
            onAbort = () => reject(signal.reason);
            signal.addEventListener("abort", onAbort, { once: true });
        });
        const results = [];
        let nextIndex = 0;
        async function worker() {
            while (nextIndex < candidates.length) {
                signal.throwIfAborted();
                const index = nextIndex++;
                const candidate = candidates[index];
                // Each worker queues only its next read. Later listings enter the
                // shared FIFO after at most four outstanding reads from this listing.
                const pending = acquire(candidate);
                try {
                    results[index] = await Promise.race([pending.promise, aborted]);
                }
                finally {
                    release(candidate, pending);
                }
            }
        }
        try {
            const workers = Array.from({ length: Math.min(4, candidates.length) }, () => worker());
            await Promise.all(workers);
            return results;
        }
        catch (error) {
            controller.abort(error);
            throw error;
        }
        finally {
            if (onAbort)
                signal.removeEventListener("abort", onAbort);
        }
    };
}
//# sourceMappingURL=import-descriptor-scheduler.js.map