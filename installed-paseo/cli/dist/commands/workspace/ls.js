import { connectToDaemon, getDaemonHost } from "../../utils/client.js";
import { toWorkspaceRow, workspaceSchema, workspaceWithBackgroundSchema, } from "./shared.js";
export async function runLsCommand(options, _command) {
    const host = getDaemonHost({ target: options.daemonTarget });
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        throw {
            code: "DAEMON_NOT_RUNNING",
            message: `Cannot connect to daemon at ${host}: ${message}`,
        };
    });
    try {
        const workspaces = [];
        let cursor;
        do {
            const payload = await client.fetchWorkspaces({
                ...(options.background ? { filter: { includeBackground: true } } : {}),
                page: { limit: 200, ...(cursor ? { cursor } : {}) },
            });
            workspaces.push(...payload.entries.map(toWorkspaceRow));
            cursor = payload.pageInfo.nextCursor ?? undefined;
        } while (cursor);
        return {
            type: "list",
            data: workspaces,
            schema: options.background ? workspaceWithBackgroundSchema : workspaceSchema,
        };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=ls.js.map