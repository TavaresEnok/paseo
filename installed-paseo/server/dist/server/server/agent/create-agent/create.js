import { expandUserPath, resolvePathFromBase } from "../../path-utils.js";
import { toWorktreeRequestError } from "../../worktree-errors.js";
import { startCreatedAgentInitialPrompt } from "../agent-prompt.js";
import { resolveCreateAgentTitles } from "../create-agent-title.js";
import { buildAgentPrompt } from "../prompt-attachments.js";
import { normalizeClientMessageId, resolveClientMessageId } from "../../client-message-id.js";
import { resolveRequiredProviderModel } from "../mcp-shared.js";
import { resolveCreateAgentIntent } from "./intent.js";
function requireResolvedWorkspaceId(workspaceId) {
    if (!workspaceId) {
        throw new Error("createAgentCommand requires a resolved workspaceId");
    }
    return workspaceId;
}
export function formatProviderModel(provider, model) {
    if (!model || provider.includes("/")) {
        return provider;
    }
    return `${provider}/${model}`;
}
function resolveProviderModel(providerValue) {
    const providerInput = providerValue.trim();
    if (providerInput.includes("/")) {
        return resolveRequiredProviderModel(providerInput);
    }
    if (!providerInput) {
        throw new Error("provider is required");
    }
    return { provider: providerInput, model: undefined };
}
export async function createAgentCommand(dependencies, input) {
    const resolved = input.kind === "session"
        ? await resolveSessionCreateAgent(dependencies, input)
        : await resolveMcpCreateAgent(dependencies, input);
    const snapshot = await dependencies.agentManager.createAgent(resolved.config, input.kind === "session" ? input.agentId : undefined, resolved.createOptions);
    if (input.kind === "session")
        await input.onAgentReady?.(snapshot);
    let liveSnapshot = snapshot;
    let initialPromptStarted = false;
    let initialPromptError = null;
    if (input.kind === "mcp") {
        input.onCreated?.({ agentId: snapshot.id, createdWorktree: resolved.createdWorktree ?? null });
    }
    const notification = input.kind === "mcp" &&
        input.notifyOnFinish &&
        input.callerAgentId &&
        resolved.prompt !== undefined
        ? await requireFinishSubscriptions(dependencies).register({
            childAgentId: snapshot.id,
            callerAgentId: input.callerAgentId,
            requireParentOwnership: !(input.detached ?? false),
        }, true)
        : undefined;
    if (resolved.prompt !== undefined) {
        const sendResult = await sendInitialPrompt(dependencies, resolved, snapshot).catch(async (error) => {
            await notification?.reject();
            throw error;
        });
        notification?.accept();
        initialPromptStarted = sendResult.started;
        liveSnapshot = sendResult.liveSnapshot;
        initialPromptError = sendResult.error ?? null;
    }
    return {
        snapshot,
        liveSnapshot,
        initialPromptStarted,
        initialPromptError,
        ...(resolved.createdWorktree ? { createdWorktree: resolved.createdWorktree } : {}),
    };
}
async function resolveSessionCreateAgent(dependencies, input) {
    const trimmedPrompt = input.initialPrompt?.trim();
    const builtSessionConfig = input.config;
    const resolvedCreateConfig = await dependencies.providerSnapshotManager.resolveCreateConfig({
        cwd: builtSessionConfig.cwd,
        provider: builtSessionConfig.provider,
        requestedMode: builtSessionConfig.modeId,
        featureValues: builtSessionConfig.featureValues,
        parent: null,
        unattended: false,
    });
    const sessionConfig = {
        ...builtSessionConfig,
        modeId: resolvedCreateConfig.modeId,
        featureValues: resolvedCreateConfig.featureValues,
    };
    const prompt = buildAgentPrompt(trimmedPrompt ?? "", input.images, input.attachments);
    const hasPromptContent = Array.isArray(prompt) ? prompt.length > 0 : prompt.length > 0;
    const clientMessageId = normalizeClientMessageId(input.clientMessageId);
    const runOptions = input.outputSchema || clientMessageId
        ? {
            ...(input.outputSchema ? { outputSchema: input.outputSchema } : {}),
            ...(clientMessageId ? { clientMessageId } : {}),
        }
        : undefined;
    const workspaceId = input.workspaceId;
    return {
        config: sessionConfig,
        createOptions: {
            labels: input.labels,
            initialPrompt: trimmedPrompt,
            env: input.env,
            initialTitle: input.provisionalTitle,
            // Paseo never persists an internal agent, so nothing could resume its
            // provider session either. Same as the daemon's own ephemeral helpers.
            ...(sessionConfig.internal ? { persistSession: false } : {}),
            workspaceId: requireResolvedWorkspaceId(workspaceId),
        },
        prompt: hasPromptContent ? prompt : undefined,
        source: input.source,
        runOptions,
        // Registration commits creation. First-turn failures belong to the created agent.
        promptFailure: "return-error",
        promptLogger: dependencies.logger.child({
            clientMessageId: resolveClientMessageId(input.clientMessageId),
        }),
    };
}
async function resolveMcpCreateAgent(dependencies, input) {
    const resolvedProviderModel = resolveProviderModel(input.provider);
    const provider = resolvedProviderModel.provider;
    const parentAgent = input.callerAgentId
        ? requireParentAgent(dependencies.agentManager, input.callerAgentId)
        : null;
    const cwd = resolveMcpInitialCwd(input, parentAgent);
    const { resolvedCwd, createdWorkspaceId, createdWorktree } = await resolveMcpCwd({
        dependencies,
        cwd,
        worktree: input.worktree,
        initialPrompt: input.initialPrompt ?? "",
        callerWorkspaceId: parentAgent?.workspaceId,
    });
    if (createdWorktree)
        input.onWorktreeCreated?.(createdWorktree);
    const intent = await resolveCreateAgentIntent({
        explicitWorkspaceId: createdWorkspaceId ?? input.workspaceId,
        caller: parentAgent
            ? { id: parentAgent.id, cwd: parentAgent.cwd, workspaceId: parentAgent.workspaceId }
            : null,
        labels: input.labels,
        childAgentDefaultLabels: input.callerContext?.childAgentDefaultLabels,
        legacyDetached: input.detached ?? false,
        resolveWorkspace: async (workspaceId) => ({ workspaceId, cwd: resolvedCwd }),
        createWorkspace: async () => ({
            workspaceId: requireResolvedWorkspaceId(await ensureWorkspaceForMcpCreate(dependencies, resolvedCwd, input.initialPrompt ?? "", parentAgent?.workspaceId)),
            cwd: resolvedCwd,
        }),
    });
    const resolvedCreateConfig = await resolveMcpProviderCreateConfig({
        dependencies,
        input,
        provider,
        resolvedCwd,
        parentAgent,
    });
    const trimmedPrompt = input.initialPrompt?.trim() ?? "";
    return {
        config: buildMcpSessionConfig({
            input,
            resolvedProviderModel,
            provider,
            resolvedCwd: intent.cwd,
            trimmedPrompt,
            resolvedMode: resolvedCreateConfig.modeId,
            resolvedFeatures: resolvedCreateConfig.featureValues,
        }),
        createOptions: {
            ...(Object.keys(intent.labels).length > 0 ? { labels: intent.labels } : {}),
            workspaceId: intent.workspaceId,
            owner: input.owner,
            env: input.env,
        },
        prompt: trimmedPrompt ? trimmedPrompt : undefined,
        source: input.callerAgentId
            ? { kind: "agent-message", agentId: input.callerAgentId }
            : undefined,
        createdWorktree,
        promptFailure: input.promptFailure ?? "log",
    };
}
function resolveMcpInitialCwd(input, parentAgent) {
    if (!parentAgent) {
        return expandUserPath(input.cwd ?? process.cwd());
    }
    return resolveChildAgentCwd({
        parentCwd: parentAgent.cwd,
        requestedCwd: input.cwd,
        lockedCwd: input.callerContext?.lockedCwd,
        allowCustomCwd: input.callerContext?.allowCustomCwd ?? true,
    });
}
async function resolveMcpProviderCreateConfig(params) {
    const passthroughConfig = params.input.config;
    return params.dependencies.providerSnapshotManager.resolveCreateConfig({
        cwd: params.resolvedCwd,
        provider: params.provider,
        requestedMode: params.input.mode ?? passthroughConfig?.modeId,
        featureValues: params.input.features ?? passthroughConfig?.featureValues,
        parent: params.parentAgent,
        unattended: params.input.unattended ?? false,
    });
}
function buildMcpSessionConfig(params) {
    const passthroughConfig = params.input.config;
    const { provisionalTitle } = resolveCreateAgentTitles({
        configTitle: passthroughConfig?.title ?? params.input.title,
        initialPrompt: params.trimmedPrompt,
    });
    const featureValues = params.resolvedFeatures ?? passthroughConfig?.featureValues;
    const config = {
        ...passthroughConfig,
        provider: params.provider,
        cwd: params.resolvedCwd,
        modeId: params.resolvedMode ?? passthroughConfig?.modeId,
        model: params.resolvedProviderModel.model ?? passthroughConfig?.model,
        thinkingOptionId: params.input.thinking ?? passthroughConfig?.thinkingOptionId,
        internal: params.input.internal ?? passthroughConfig?.internal,
    };
    if (provisionalTitle) {
        config.title = provisionalTitle;
    }
    if (featureValues) {
        config.featureValues = featureValues;
    }
    return config;
}
async function ensureWorkspaceForMcpCreate(dependencies, cwd, initialPrompt, callerWorkspaceId) {
    if (!dependencies.ensureWorkspaceForCreate) {
        return undefined;
    }
    return dependencies.ensureWorkspaceForCreate(cwd, { prompt: initialPrompt }, { callerWorkspaceId });
}
async function sendInitialPrompt(dependencies, resolved, snapshot) {
    try {
        const prompt = resolved.prompt;
        if (prompt === undefined) {
            return { started: false, liveSnapshot: snapshot };
        }
        const liveSnapshot = await startCreatedAgentInitialPrompt({
            agentStorage: dependencies.agentStorage,
            agentManager: dependencies.agentManager,
            agentId: snapshot.id,
            snapshot,
            prompt,
            source: resolved.source,
            runOptions: resolved.runOptions,
            logger: resolved.promptLogger ?? dependencies.logger,
        });
        return { started: true, liveSnapshot };
    }
    catch (error) {
        if (resolved.promptFailure === "throw") {
            throw error;
        }
        if (resolved.promptFailure === "return-error") {
            return {
                started: false,
                liveSnapshot: dependencies.agentManager.getAgent(snapshot.id) ?? snapshot,
                error,
            };
        }
        dependencies.logger.error({ err: error, agentId: snapshot.id }, "Failed to run initial prompt");
        return { started: false, liveSnapshot: snapshot };
    }
}
function requireParentAgent(agentManager, parentAgentId) {
    const parentAgent = agentManager.getAgent(parentAgentId);
    if (!parentAgent) {
        throw new Error(`Parent agent ${parentAgentId} not found`);
    }
    return parentAgent;
}
function resolveChildAgentCwd(params) {
    const lockedCwd = params.lockedCwd?.trim();
    if (lockedCwd) {
        return expandUserPath(lockedCwd);
    }
    const requestedCwd = params.requestedCwd?.trim();
    if (!requestedCwd || !params.allowCustomCwd) {
        return params.parentCwd;
    }
    return resolvePathFromBase(params.parentCwd, requestedCwd);
}
async function createMcpWorktree(options) {
    try {
        if (!options.createPaseoWorktree) {
            throw new Error("Paseo worktree service is not configured");
        }
        return await options.createPaseoWorktree(options.input, options.resolveDefaultBranch ? { resolveDefaultBranch: options.resolveDefaultBranch } : {});
    }
    catch (error) {
        throw toWorktreeRequestError(error);
    }
}
async function resolveMcpCwd(params) {
    const { dependencies, worktree } = params;
    if (!worktree) {
        return { resolvedCwd: params.cwd };
    }
    const shouldCreateWorktree = Boolean(worktree.worktreeName || worktree.refName || worktree.action || worktree.githubPrNumber);
    if (!shouldCreateWorktree) {
        return { resolvedCwd: params.cwd };
    }
    if (worktree.worktreeName &&
        !worktree.baseBranch &&
        !worktree.refName &&
        !worktree.action &&
        worktree.githubPrNumber === undefined) {
        throw new Error("baseBranch is required when creating a worktree");
    }
    const baseBranch = worktree.baseBranch;
    const createdWorktree = await createMcpWorktree({
        input: {
            cwd: params.cwd,
            callerWorkspaceId: params.callerWorkspaceId,
            worktreeSlug: worktree.worktreeName,
            branchName: worktree.branchName,
            refName: worktree.refName,
            action: worktree.action,
            githubPrNumber: worktree.githubPrNumber,
            firstAgentContext: { prompt: params.initialPrompt },
            paseoHome: dependencies.paseoHome,
            worktreesRoot: dependencies.worktreesRoot,
        },
        createPaseoWorktree: dependencies.createPaseoWorktree,
        resolveDefaultBranch: baseBranch ? async () => baseBranch : undefined,
    });
    return {
        resolvedCwd: createdWorktree.workspace.cwd,
        createdWorkspaceId: createdWorktree.workspace.workspaceId,
        createdWorktree,
    };
}
function requireFinishSubscriptions(dependencies) {
    if (!dependencies.finishSubscriptions)
        throw new Error("Finish subscriptions are not configured");
    return dependencies.finishSubscriptions;
}
//# sourceMappingURL=create.js.map