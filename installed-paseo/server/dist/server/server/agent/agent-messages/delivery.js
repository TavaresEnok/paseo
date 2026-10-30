import { randomUUID } from "node:crypto";
import { prepareAgentMessage } from "./envelope.js";
/** Recipient-owned agent delivery. Human prompts never enter this module. */
export function createAgentMessageDelivery(dependencies) {
    const schedule = dependencies.schedule ??
        ((delayMs, callback) => {
            const timer = setTimeout(callback, delayMs);
            return () => clearTimeout(timer);
        });
    const pending = new Map();
    const dispatching = new Map();
    let closed = false;
    let closing;
    function dispatch(recipientId, messages) {
        const prompts = messages.map((message) => prepareAgentMessage(message.prompt, message.source, message.receipt.messageId).prompt);
        const prompt = prompts.every((entry) => typeof entry === "string")
            ? prompts.join("\n\n")
            : prompts.flatMap((entry) => typeof entry === "string" ? [{ type: "text", text: entry }] : entry);
        const request = {
            recipientId,
            messageIds: messages.map((message) => message.receipt.messageId),
            prompt,
            activeTurnBehavior: messages[0].activeTurnBehavior ?? "steer",
            sessionMode: messages.find((message) => message.sessionMode)?.sessionMode,
            clearPendingPermissions: messages.some((message) => message.clearPendingPermissions),
            unarchive: messages.some((message) => message.unarchive !== false),
            onDispatch: (disposition) => {
                for (const message of messages) {
                    try {
                        message.onDispatch?.(disposition);
                    }
                    catch (error) {
                        dependencies.onError(error, request);
                    }
                }
            },
        };
        const previous = dispatching.get(recipientId) ?? Promise.resolve();
        const dispatched = previous
            .catch(() => undefined)
            .then(async () => {
            try {
                for (const message of messages)
                    message.beforeDispatch?.();
                const disposition = await dependencies.dispatch(request);
                for (const message of messages)
                    message.resolve(disposition);
                return undefined;
            }
            catch (error) {
                for (const message of messages)
                    message.reject(error);
                dependencies.onError(error, request);
                throw error;
            }
        });
        dispatching.set(recipientId, dispatched);
        void dispatched
            .finally(() => {
            if (dispatching.get(recipientId) === dispatched)
                dispatching.delete(recipientId);
        })
            .catch(() => undefined);
    }
    function flush(recipientId) {
        const entry = pending.get(recipientId);
        if (!entry)
            return;
        pending.delete(recipientId);
        entry.cancel();
        let group = [];
        let mode;
        for (const message of entry.messages) {
            // Explicitly conflicting send options require separate, ordered dispatches.
            if (group.length &&
                ((message.activeTurnBehavior ?? "steer") !== (group[0].activeTurnBehavior ?? "steer") ||
                    (mode && message.sessionMode && mode !== message.sessionMode))) {
                dispatch(recipientId, group);
                group = [];
                mode = undefined;
            }
            group.push(message);
            mode ?? (mode = message.sessionMode);
        }
        if (group.length)
            dispatch(recipientId, group);
    }
    return {
        enqueue(message) {
            if (closed)
                throw new Error("Agent message delivery is closed");
            let resolve;
            let reject;
            const dispatched = new Promise((accepted, failed) => {
                resolve = accepted;
                reject = failed;
            });
            void dispatched.catch(() => undefined);
            const receipt = {
                status: "queued",
                messageId: message.messageId ?? randomUUID(),
                dispatched,
            };
            const entry = pending.get(message.recipientId) ?? { messages: [], cancel: () => { } };
            entry.cancel();
            entry.messages.push({ ...message, receipt, resolve, reject });
            entry.cancel = schedule(2000, () => flush(message.recipientId));
            pending.set(message.recipientId, entry);
            return receipt;
        },
        async waitForDispatch(recipientId, signal) {
            signal.throwIfAborted();
            const admitted = pending.get(recipientId)?.messages.map((message) => message.receipt.dispatched) ?? [];
            let aborted;
            const cancellation = new Promise((_resolve, reject) => {
                aborted = () => reject(new DOMException("Wait aborted", "AbortError"));
                signal.addEventListener("abort", aborted, { once: true });
            });
            try {
                await Promise.race([
                    Promise.all([dispatching.get(recipientId), ...admitted]),
                    cancellation,
                ]);
            }
            finally {
                signal.removeEventListener("abort", aborted);
            }
        },
        close() {
            if (closing)
                return closing;
            closed = true;
            for (const recipientId of pending.keys())
                flush(recipientId);
            // Each failure is reported and rejects its receipts; shutdown still drains other recipients.
            closing = Promise.allSettled(dispatching.values()).then(() => undefined);
            return closing;
        },
    };
}
//# sourceMappingURL=delivery.js.map