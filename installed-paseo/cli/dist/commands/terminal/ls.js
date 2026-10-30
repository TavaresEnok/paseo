import { connectTerminalClient, toTerminalCommandError, } from "./shared.js";
import { terminalSchema } from "./schema.js";
export async function runLsCommand(options, _command) {
    const { client, close } = await connectTerminalClient(options.daemonTarget);
    const cwd = options.all || options.workspace ? undefined : (options.cwd ?? process.cwd());
    try {
        const payload = await client.terminals.list({ cwd, workspaceId: options.workspace });
        return {
            type: "list",
            data: payload.entries,
            schema: terminalSchema,
        };
    }
    catch (err) {
        throw toTerminalCommandError("TERMINAL_LIST_FAILED", "list terminals", err);
    }
    finally {
        await close().catch(() => { });
    }
}
//# sourceMappingURL=ls.js.map