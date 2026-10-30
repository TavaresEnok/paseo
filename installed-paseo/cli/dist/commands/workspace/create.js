import { connectToDaemon, getDaemonHost } from "../../utils/client.js";
import { resolveCallerAgentId } from "../../utils/caller-agent.js";
import { toWorkspaceRow, workspaceSchema } from "./shared.js";
function assertOptionsAbsent(values, message) {
    if (values.some((value) => value !== undefined)) {
        throw new Error(message);
    }
}
function buildLocalWorkspaceSource(options, path) {
    assertOptionsAbsent([
        options.mode,
        options.worktreeSlug,
        options.newBranch,
        options.base,
        options.branch,
        options.prNumber,
        options.forge,
    ], "Worktree options require --isolation worktree");
    return {
        kind: "directory",
        path,
        ...(options.project ? { projectId: options.project } : {}),
    };
}
function buildBranchOffSource(options, source) {
    assertOptionsAbsent([options.branch, options.prNumber, options.forge], "--branch, --pr-number, and --forge require a checkout mode");
    return {
        ...source,
        action: "branch-off",
        ...(options.newBranch ? { branchName: options.newBranch } : {}),
        ...(options.base ? { baseBranch: options.base } : {}),
    };
}
function buildBranchCheckoutSource(options, source) {
    if (!options.branch) {
        throw new Error("--branch is required for --mode checkout-branch");
    }
    assertOptionsAbsent([options.newBranch, options.base, options.prNumber, options.forge], "--new-branch, --base, --pr-number, and --forge are not valid for --mode checkout-branch");
    return { ...source, action: "checkout", refName: options.branch };
}
function buildPullRequestCheckoutSource(options, source) {
    if (options.prNumber === undefined || options.prNumber === "") {
        throw new Error("--pr-number is required for --mode checkout-pr");
    }
    const prNumber = Number(options.prNumber);
    if (!Number.isInteger(prNumber) || prNumber <= 0) {
        throw new Error("--pr-number must be a positive integer");
    }
    assertOptionsAbsent([options.newBranch, options.base, options.branch], "--new-branch, --base, and --branch are not valid for --mode checkout-pr");
    return {
        ...source,
        action: "checkout",
        checkoutSource: {
            kind: "change_request",
            ...(options.forge ? { forge: options.forge } : {}),
            number: prNumber,
        },
    };
}
function buildWorktreeWorkspaceSource(options, path) {
    const source = {
        kind: "worktree",
        ...(path ? { cwd: path } : {}),
        ...(options.project ? { projectId: options.project } : {}),
        ...(options.worktreeSlug ? { worktreeSlug: options.worktreeSlug } : {}),
    };
    switch (options.mode ?? "branch-off") {
        case "branch-off":
            return buildBranchOffSource(options, source);
        case "checkout-branch":
            return buildBranchCheckoutSource(options, source);
        case "checkout-pr":
            return buildPullRequestCheckoutSource(options, source);
        default:
            throw new Error(`Unsupported worktree mode: ${String(options.mode)}`);
    }
}
export function buildWorkspaceSource(options) {
    if (options.isolation === "local") {
        return buildLocalWorkspaceSource(options, options.path ?? process.cwd());
    }
    if (options.isolation === "worktree") {
        const sourcePath = options.path ?? (options.project ? undefined : process.cwd());
        return buildWorktreeWorkspaceSource(options, sourcePath);
    }
    throw new Error(`Unsupported workspace isolation: ${String(options.isolation)}`);
}
export async function runCreateCommand(options, _command) {
    const host = getDaemonHost({ target: options.daemonTarget });
    const client = await connectToDaemon({ target: options.daemonTarget }).catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        throw {
            code: "DAEMON_NOT_RUNNING",
            message: `Cannot connect to daemon at ${host}: ${message}`,
        };
    });
    try {
        const callerAgentId = await resolveCallerAgentId(client);
        const payload = await client.createWorkspace({
            source: buildWorkspaceSource(options),
            ...(options.title ? { title: options.title } : {}),
            ...(options.background !== undefined ? { background: options.background } : {}),
            ...(callerAgentId ? { callerAgentId } : {}),
        });
        if (!payload.workspace) {
            throw new Error(payload.error ?? "Workspace creation failed");
        }
        return { type: "single", data: toWorkspaceRow(payload.workspace), schema: workspaceSchema };
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error)
            throw error;
        const message = error instanceof Error ? error.message : String(error);
        throw { code: "WORKSPACE_CREATE_FAILED", message };
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=create.js.map