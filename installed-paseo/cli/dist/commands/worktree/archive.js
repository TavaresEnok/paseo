import path from "path";
import { connectToDaemon, getDaemonHost } from "../../utils/client.js";
import { resolveRepositoryDirectory } from "./repository-directory.js";
/** Schema for archive command output */
export const archiveSchema = {
    idField: "name",
    columns: [
        { header: "NAME", field: "name" },
        { header: "STATUS", field: "status" },
        {
            header: "REMOVED AGENTS",
            field: (item) => (item.removedAgents.length > 0 ? item.removedAgents.join(", ") : "-"),
        },
    ],
};
export async function runArchiveCommand(nameArg, options, _command) {
    return runArchiveCommandWithDeps(nameArg, options, { connectToDaemon });
}
export async function runArchiveCommandWithDeps(nameArg, options, deps) {
    const host = getDaemonHost({ target: options.daemonTarget });
    const cwd = resolveRepositoryDirectory(options);
    // Validate arguments
    if (!nameArg || nameArg.trim().length === 0) {
        const error = {
            code: "MISSING_WORKTREE_NAME",
            message: "Worktree name is required",
            details: "Usage: paseo worktree archive <name>",
        };
        throw error;
    }
    let client;
    try {
        client = await deps.connectToDaemon({ target: options.daemonTarget });
    }
    catch (err) {
        if (err && typeof err === "object" && "code" in err)
            throw err;
        const message = err instanceof Error ? err.message : String(err);
        const error = {
            code: "DAEMON_NOT_RUNNING",
            message: `Cannot connect to daemon at ${host}: ${message}`,
            details: "Start the daemon with: paseo daemon start",
        };
        throw error;
    }
    try {
        // Get the list of worktrees first to resolve the name
        const listResponse = await client.getPaseoWorktreeList({ cwd });
        if (listResponse.error) {
            const error = {
                code: "WORKTREE_LIST_FAILED",
                message: `Failed to list worktrees: ${listResponse.error.message}`,
            };
            throw error;
        }
        // Find the worktree by name or branch
        const worktree = listResponse.worktrees.find((wt) => {
            const name = path.basename(wt.worktreePath);
            return name === nameArg || wt.branchName === nameArg;
        });
        if (!worktree) {
            const error = {
                code: "WORKTREE_NOT_FOUND",
                message: `Worktree not found: ${nameArg}`,
                details: 'Use "paseo worktree ls" to list available worktrees',
            };
            throw error;
        }
        // Archive the worktree. scope:"worktree" archives every active workspace on
        // the directory and then removes the directory (Paseo-owned gated).
        const response = await client.archivePaseoWorktree({
            worktreePath: worktree.worktreePath,
            scope: "worktree",
        });
        await client.close();
        if (response.error) {
            const error = {
                code: "WORKTREE_ARCHIVE_FAILED",
                message: `Failed to archive worktree: ${response.error.message}`,
            };
            throw error;
        }
        const worktreeName = path.basename(worktree.worktreePath) || nameArg;
        return {
            type: "single",
            data: {
                name: worktreeName,
                status: "archived",
                removedAgents: response.removedAgents ?? [],
            },
            schema: archiveSchema,
        };
    }
    catch (err) {
        await client.close().catch(() => { });
        // Re-throw CommandError as-is
        if (err && typeof err === "object" && "code" in err) {
            throw err;
        }
        const message = err instanceof Error ? err.message : String(err);
        const error = {
            code: "WORKTREE_ARCHIVE_FAILED",
            message: `Failed to archive worktree: ${message}`,
        };
        throw error;
    }
}
//# sourceMappingURL=archive.js.map