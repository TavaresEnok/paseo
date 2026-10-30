import { connectTerminalClient, toTerminalCommandError, } from "./shared.js";
import { terminalSchema } from "./schema.js";
export async function runCreateCommand(options, _command) {
    const { client, close } = await connectTerminalClient(options.daemonTarget);
    try {
        const cwd = options.cwd ?? (options.workspace ? undefined : process.cwd());
        const workspaceId = options.workspace ?? (await client.workspaces.open(options.cwd ?? process.cwd())).id;
        const terminal = await client.terminals.create({
            workspaceId,
            cwd,
            name: options.name,
        });
        const snapshot = terminal.current();
        if (!snapshot)
            throw new Error("The daemon did not create a terminal");
        return {
            type: "single",
            data: snapshot,
            schema: terminalSchema,
        };
    }
    catch (err) {
        throw toTerminalCommandError("TERMINAL_CREATE_FAILED", "create terminal", err);
    }
    finally {
        await close().catch(() => { });
    }
}
//# sourceMappingURL=create.js.map