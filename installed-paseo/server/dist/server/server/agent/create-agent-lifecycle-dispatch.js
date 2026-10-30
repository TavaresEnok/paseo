import { randomUUID } from "node:crypto";
import { isPaseoOwnedWorktreeCwd } from "../../utils/worktree.js";
import { archiveByScope } from "../workspace-archive-service.js";
const inactiveRegistration = { cancel: async () => undefined };
export class CreateAgentLifecycleDispatch {
    constructor(dependencies) {
        this.dependencies = dependencies;
        this.autoArchiveAgentIds = new Set();
    }
    async createWorktreeForRequest(input) {
        const target = input.target;
        if (!target)
            return null;
        const placement = { cwd: input.cwd };
        switch (target.mode) {
            case "branch-off":
                placement.action = "branch-off";
                placement.worktreeSlug = target.newBranch;
                placement.refName = target.base;
                break;
            case "checkout-branch":
                placement.action = "checkout";
                placement.refName = target.branch;
                break;
            case "checkout-pr":
                placement.githubPrNumber = target.prNumber;
                break;
        }
        const base = target.mode === "branch-off" ? target.base : undefined;
        return this.dependencies.createPaseoWorktreeWorkflow({
            ...placement,
            background: input.background,
            callerWorkspaceId: input.callerWorkspaceId,
            firstAgentContext: input.firstAgentContext,
            paseoHome: this.dependencies.paseoHome,
            worktreesRoot: this.dependencies.worktreesRoot,
        }, base ? { resolveDefaultBranch: async () => base } : undefined);
    }
    registerAutoArchiveIfRequested(input) {
        if (input.autoArchive !== true) {
            return inactiveRegistration;
        }
        return this.registerAutoArchiveOnTerminalState(input.agentId, toAutoArchiveTarget(input.createdWorktree));
    }
    async cleanupCreatedWorktreeAfterFailedAgentCreate(input) {
        const { createdWorktree, createdAgentId } = input;
        if (!createdWorktree || createdAgentId) {
            return;
        }
        await this.archiveAutoCreatedWorktree({
            agentId: null,
            createdWorktree,
        }).catch((archiveError) => {
            this.dependencies.logger.warn({
                err: archiveError,
                worktreePath: createdWorktree.worktree.worktreePath,
            }, "Failed to clean up worktree after create_agent_request failed");
        });
    }
    registerAutoArchiveOnTerminalState(agentId, target) {
        return registerAgentAutoArchive({
            agentManager: this.dependencies.agentManager,
            agentId,
            archive: () => this.autoArchiveAgentOnce(agentId, target),
        });
    }
    async autoArchiveAgentOnce(agentId, target) {
        if (this.autoArchiveAgentIds.has(agentId)) {
            return;
        }
        this.autoArchiveAgentIds.add(agentId);
        try {
            if (target.kind === "created-worktree") {
                await this.archiveAutoCreatedWorktree({
                    agentId,
                    createdWorktree: target.result,
                });
                return;
            }
            await this.dependencies.archiveAgentForClose(agentId);
        }
        catch (error) {
            this.dependencies.logger.warn({ err: error, agentId }, "Failed to auto-archive agent");
        }
    }
    async archiveAutoCreatedWorktree(options) {
        const { createdWorktree } = options;
        const worktreePath = createdWorktree.worktree.worktreePath;
        const ownership = await isPaseoOwnedWorktreeCwd(worktreePath, {
            paseoHome: this.dependencies.paseoHome,
            worktreesRoot: this.dependencies.worktreesRoot,
        });
        if (!ownership.allowed) {
            throw new Error("Auto-created worktree is not a Paseo-owned worktree");
        }
        await archiveByScope({
            paseoHome: this.dependencies.paseoHome,
            paseoWorktreesBaseRoot: this.dependencies.worktreesRoot,
            github: this.dependencies.github,
            workspaceGitService: this.dependencies.workspaceGitService,
            agentManager: this.dependencies.agentManager,
            agentStorage: this.dependencies.agentStorage,
            findWorkspaceIdForCwd: this.dependencies.findWorkspaceIdForCwd,
            listActiveWorkspaces: this.dependencies.listActiveWorkspaces,
            archiveWorkspaceRecord: this.dependencies.archiveWorkspaceRecord,
            emitWorkspaceUpdatesForWorkspaceIds: this.dependencies.emitWorkspaceUpdatesForWorkspaceIds,
            markWorkspaceArchiving: this.dependencies.markWorkspaceArchiving,
            clearWorkspaceArchiving: this.dependencies.clearWorkspaceArchiving,
            killTerminalsForWorkspace: this.dependencies.killTerminalsForWorkspace,
            sessionLogger: this.dependencies.logger,
        }, {
            scope: { kind: "workspace", workspaceId: createdWorktree.workspace.workspaceId },
            requestId: randomUUID(),
        });
        if (options.agentId) {
            await this.dependencies.emitAgentRemove(options.agentId);
        }
    }
}
export function registerAgentAutoArchive(input) {
    let unsubscribe = null;
    let archiveTask = null;
    const release = () => {
        if (!unsubscribe)
            return;
        const subscribed = unsubscribe;
        unsubscribe = null;
        subscribed();
    };
    const registration = {
        async cancel() {
            release();
            await archiveTask;
        },
    };
    unsubscribe = input.agentManager.subscribe((event) => {
        if (event.type !== "agent_stream")
            return;
        if (event.event.type !== "turn_completed" &&
            event.event.type !== "turn_failed" &&
            event.event.type !== "turn_canceled") {
            return;
        }
        release();
        archiveTask = input.archive();
    }, { agentId: input.agentId, replayState: false });
    return registration;
}
function toAutoArchiveTarget(createdWorktree) {
    return createdWorktree
        ? { kind: "created-worktree", result: createdWorktree }
        : { kind: "agent-only" };
}
//# sourceMappingURL=create-agent-lifecycle-dispatch.js.map