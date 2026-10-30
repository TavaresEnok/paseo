import { Command } from "commander";
import { resolveHookActivity } from "@getpaseo/server/agent-hooks";
export function createHooksCommand() {
    return new Command("hooks")
        .description("Record agent hook activity")
        .argument("<agent>", "Agent hook source")
        .argument("<event>", "Agent hook event")
        .action((agent, event) => runHooksCommand(agent, event));
}
export async function runHooksCommand(agent, event, runtime = {
    env: process.env,
    input: process.stdin,
    fetch,
}) {
    const target = resolveTarget(runtime.env);
    if (!target)
        return;
    const state = await resolveHookActivity({
        provider: agent,
        event,
        input: {
            isTTY: runtime.input.isTTY,
            read: () => readInput(runtime.input),
        },
    });
    if (!state)
        return;
    await postActivity(target, state, runtime.fetch);
}
function resolveTarget(env) {
    const terminalId = env.PASEO_TERMINAL_ID;
    const token = env.PASEO_ACTIVITY_TOKEN;
    const url = env.PASEO_TERMINAL_ACTIVITY_URL;
    if (!terminalId || !token || !url)
        return null;
    return { terminalId, token, url };
}
async function readInput(input) {
    const iterator = input[Symbol.asyncIterator]();
    const chunks = [];
    while (true) {
        const next = await withTimeout(iterator.next(), 100);
        if (!next) {
            await iterator.return?.();
            return null;
        }
        if (next.done)
            return chunks.join("");
        chunks.push(String(next.value));
    }
}
async function withTimeout(promise, ms) {
    let timeout;
    try {
        return await Promise.race([
            promise,
            new Promise((resolve) => {
                timeout = setTimeout(() => resolve(null), ms);
            }),
        ]);
    }
    finally {
        if (timeout)
            clearTimeout(timeout);
    }
}
async function postActivity(target, state, send) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 500);
    try {
        await send(target.url, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
                terminalId: target.terminalId,
                token: target.token,
                state,
            }),
            signal: controller.signal,
        });
    }
    catch {
        return;
    }
    finally {
        clearTimeout(timeout);
    }
}
//# sourceMappingURL=hooks.js.map