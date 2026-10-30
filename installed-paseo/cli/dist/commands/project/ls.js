import { buildDaemonConnectionCommandError, connectToDaemon } from "../../utils/client.js";
import { projectSchema, toProjectRow } from "./shared.js";
export async function runLsCommand(options, _command) {
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        throw buildDaemonConnectionCommandError({ target: options.daemonTarget, error });
    });
    try {
        const payload = await client.listProjects();
        return {
            type: "list",
            data: payload.projects.map(toProjectRow),
            schema: projectSchema,
        };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=ls.js.map