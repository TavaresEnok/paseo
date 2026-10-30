import { connectTerminalClient, resolveTerminalId, toTerminalCommandError, } from "./shared.js";
import { terminalKillSchema } from "./schema.js";
export async function runKillCommand(terminalId, options, _command) {
    const { client, close } = await connectTerminalClient(options.daemonTarget);
    try {
        const resolvedId = await requireTerminalId(client, terminalId);
        await client.terminals.ref(resolvedId).kill();
        return {
            type: "single",
            data: {
                terminalId: resolvedId,
                success: true,
            },
            schema: terminalKillSchema,
        };
    }
    catch (err) {
        throw toTerminalCommandError("TERMINAL_KILL_FAILED", "kill terminal", err);
    }
    finally {
        await close().catch(() => { });
    }
}
async function requireTerminalId(client, terminalId) {
    const resolvedId = await resolveTerminalId(client, terminalId);
    if (resolvedId) {
        return resolvedId;
    }
    const error = {
        code: "TERMINAL_NOT_FOUND",
        message: `No terminal found matching: ${terminalId}`,
        details: "Use `paseo terminal ls --all` to list available terminals.",
    };
    throw error;
}
//# sourceMappingURL=kill.js.map