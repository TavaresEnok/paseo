import os from "node:os";
import { raceProviderRefreshAbort } from "../../provider-refresh-deadline.js";
import { terminateWithTreeKill } from "../../../../utils/tree-kill.js";
import { claudeQuery } from "./query.js";
// The curated catalog survives a failed or slow probe. This process never receives
// a prompt and must not persist a session or launch user MCP servers/hooks.
export async function discoverClaudeModels(options, openQuery = claudeQuery) {
    const controller = new AbortController();
    const signal = options.signal
        ? AbortSignal.any([options.signal, controller.signal])
        : controller.signal;
    const timer = setTimeout(() => controller.abort(new Error("Claude model discovery timed out")), 5000);
    let endInput;
    const ended = new Promise((resolve) => {
        endInput = resolve;
    });
    const input = {
        [Symbol.asyncIterator]() {
            return {
                next: async () => {
                    await ended;
                    return { done: true, value: undefined };
                },
            };
        },
    };
    let query;
    let child;
    try {
        signal.throwIfAborted();
        const binary = await raceProviderRefreshAbort(signal, options.resolveBinary());
        query = openQuery({
            prompt: input,
            options: {
                pathToClaudeCodeExecutable: binary,
                cwd: os.homedir(),
                env: options.env,
                persistSession: false,
                tools: [],
                mcpServers: {},
                strictMcpConfig: true,
                settingSources: ["user"],
                settings: { disableAllHooks: true },
                abortController: controller,
            },
        }, {
            runtimeSettings: options.runtimeSettings,
            onChildProcess: (process) => {
                child = process;
            },
        });
        return await raceProviderRefreshAbort(signal, query.supportedModels());
    }
    finally {
        clearTimeout(timer);
        endInput();
        try {
            query?.close();
        }
        finally {
            if (child) {
                await terminateWithTreeKill(child, { gracefulTimeoutMs: 200, forceTimeoutMs: 200 });
            }
        }
    }
}
//# sourceMappingURL=model-discovery.js.map