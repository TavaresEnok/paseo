import { buildDaemonConnectionCommandError, connectToDaemon } from "../../utils/client.js";
const projectRenameSchema = {
    idField: "projectId",
    columns: [
        { header: "PROJECT ID", field: "projectId", width: 20 },
        { header: "NAME", field: "name", width: 30 },
    ],
};
export function resolveProjectName(input) {
    if (input.reset) {
        if (input.name !== undefined) {
            throw {
                code: "INVALID_OPTIONS",
                message: "--reset cannot be combined with a name",
            };
        }
        return null;
    }
    const name = input.name?.trim() ?? "";
    if (name.length === 0) {
        throw {
            code: "MISSING_NAME",
            message: "Project name cannot be empty",
            details: "Usage: paseo project rename <project-id> <name> | --reset",
        };
    }
    return name;
}
export async function runRenameCommand(projectId, nameArg, options, _command) {
    const name = resolveProjectName({ name: nameArg, reset: options.reset });
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        throw buildDaemonConnectionCommandError({ target: options.daemonTarget, error });
    });
    try {
        const applied = await client.renameProject(projectId, name);
        return {
            type: "single",
            data: { projectId, name: applied.customName },
            schema: projectRenameSchema,
        };
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error)
            throw error;
        const message = error instanceof Error ? error.message : String(error);
        throw { code: "PROJECT_RENAME_FAILED", message };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=rename.js.map