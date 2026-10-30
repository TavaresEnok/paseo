import path from "node:path";
import { buildDaemonConnectionCommandError, connectToDaemon } from "../../utils/client.js";
import { projectSchema, toProjectRow } from "./shared.js";
export function resolveProjectPath(input) {
    if (input.daemonTarget) {
        if (input.pathArg === undefined) {
            throw {
                code: "MISSING_PATH",
                message: "Project path is required when targeting a daemon explicitly",
                details: "Usage: paseo project create <path> --host <host>",
            };
        }
        return input.pathArg;
    }
    return path.resolve(input.cwd, input.pathArg ?? ".");
}
export async function runCreateCommand(pathArg, options, _command) {
    const projectPath = resolveProjectPath({
        pathArg,
        cwd: process.cwd(),
        daemonTarget: options.daemonTarget.kind === "endpoint" ? options.daemonTarget.host : undefined,
    });
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        throw buildDaemonConnectionCommandError({ target: options.daemonTarget, error });
    });
    try {
        const payload = await client.addProject(projectPath);
        if (!payload.project) {
            throw new Error(payload.error ?? "Project creation failed");
        }
        return { type: "single", data: toProjectRow(payload.project), schema: projectSchema };
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error)
            throw error;
        const message = error instanceof Error ? error.message : String(error);
        throw { code: "PROJECT_CREATE_FAILED", message };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=create.js.map