import type { Logger } from "pino";
import { type FirstAgentContext, type SessionInboundMessage, type SessionOutboundMessage, type WorkspaceSetupSnapshot, type WorkspaceDescriptorPayload } from "./messages.js";
import type { PersistedWorkspaceRecord } from "./workspace-registry.js";
import type { WorkspaceGitService } from "./workspace-git-service.js";
import type { TerminalManager } from "../terminal/terminal-manager.js";
import type { ServiceProxySubsystem } from "./service-proxy.js";
import type { WorkspaceScriptRuntimeStore } from "./workspace-script-runtime-store.js";
import { type WorktreeConfig } from "../utils/worktree.js";
import type { CreatePaseoWorktreeInput, CreatePaseoWorktreeResult } from "./paseo-worktree-service.js";
import type { ArchiveDependencies } from "./workspace-archive-service.js";
import type { WorkspaceSetupOperation } from "./workspace-setup-runtime.js";
type EmitSessionMessage = (message: SessionOutboundMessage) => void;
interface CreatePaseoWorktreeInBackgroundDependencies {
    paseoHome?: string;
    worktreesRoot?: string;
    emitWorkspaceUpdateForWorkspaceId: (workspaceId: string) => Promise<void>;
    cacheWorkspaceSetupSnapshot: (workspaceId: string, snapshot: WorkspaceSetupSnapshot) => void;
    emit: EmitSessionMessage;
    sessionLogger: Logger;
    terminalManager: TerminalManager | null;
    serviceProxy: ServiceProxySubsystem | null;
    scriptRuntimeStore: WorkspaceScriptRuntimeStore | null;
    getDaemonTcpPort: (() => number | null) | null;
    getDaemonTcpHost: (() => string | null) | null;
    serviceProxyPublicBaseUrl?: string | null;
    onScriptsChanged: ((workspaceId: string, workspaceDirectory: string) => void) | null;
}
interface CreatePaseoWorktreeWorkflowDependencies extends CreatePaseoWorktreeInBackgroundDependencies {
    createPaseoWorktree: (input: CreatePaseoWorktreeInput, options?: {
        resolveDefaultBranch?: (repoRoot: string) => Promise<string>;
    }) => Promise<CreatePaseoWorktreeResult>;
    warmWorkspaceGitData: (workspace: PersistedWorkspaceRecord) => Promise<void>;
    autoNameWorkspaceBranchForFirstAgent: (input: {
        workspace: PersistedWorkspaceRecord;
        firstAgentContext: FirstAgentContext;
    }) => void;
    startWorkspaceSetup?: (workspaceId: string, operation: WorkspaceSetupOperation) => void;
    assertWorkspaceAutomationAllowed?: (workspaceId: string) => Promise<void>;
}
export type CreatePaseoWorktreeWorkflowResult = CreatePaseoWorktreeResult;
export type CreatePaseoWorktreeWorkflowFn = (input: CreatePaseoWorktreeInput, options?: {
    resolveDefaultBranch?: (repoRoot: string) => Promise<string>;
}) => Promise<CreatePaseoWorktreeWorkflowResult>;
interface HandleWorkspaceSetupStatusRequestDependencies {
    emit: EmitSessionMessage;
    workspaceSetupSnapshots: Pick<ReadonlyMap<string, WorkspaceSetupSnapshot>, "get">;
    getWorkspace: (workspaceId: string) => Promise<PersistedWorkspaceRecord | null>;
}
interface HandleWorkspaceSetupRunRequestDependencies extends CreatePaseoWorktreeInBackgroundDependencies {
    getWorkspace: (workspaceId: string) => Promise<PersistedWorkspaceRecord | null>;
    clearAutomationBlock: (workspaceId: string) => Promise<boolean>;
    startWorkspaceSetup: (workspaceId: string, operation: WorkspaceSetupOperation) => void;
}
interface HandleCreatePaseoWorktreeRequestDependencies {
    paseoHome?: string;
    worktreesRoot?: string;
    describeWorkspaceRecord: (result: CreatePaseoWorktreeResult) => Promise<WorkspaceDescriptorPayload>;
    emit: EmitSessionMessage;
    sessionLogger: Logger;
    createPaseoWorktreeWorkflow: (input: CreatePaseoWorktreeInput) => Promise<CreatePaseoWorktreeWorkflowResult>;
}
export declare function assertSafeGitRef(ref: string, label: string): void;
export declare function handlePaseoWorktreeListRequest(dependencies: {
    emit: EmitSessionMessage;
    paseoHome?: string;
    workspaceGitService: WorkspaceGitService;
}, msg: Extract<SessionInboundMessage, {
    type: "paseo_worktree_list_request";
}>): Promise<void>;
export declare function handlePaseoWorktreeArchiveRequest(dependencies: Omit<ArchiveDependencies, "emitWorkspaceUpdatesForWorkspaceIds" | "workspaceGitService"> & {
    emit: EmitSessionMessage;
    workspaceGitService: Pick<WorkspaceGitService, "getSnapshot" | "listWorktrees" | "invalidateWorktrees">;
    emitWorkspaceUpdatesForWorkspaceIds: (workspaceIds: Iterable<string>) => Promise<void>;
}, msg: Extract<SessionInboundMessage, {
    type: "paseo_worktree_archive_request";
}>): Promise<void>;
export declare function handleCreatePaseoWorktreeRequest(dependencies: HandleCreatePaseoWorktreeRequestDependencies, request: Extract<SessionInboundMessage, {
    type: "create_paseo_worktree_request";
}>): Promise<void>;
export declare function createPaseoWorktreeWorkflow(dependencies: CreatePaseoWorktreeWorkflowDependencies, input: CreatePaseoWorktreeInput, options?: {
    resolveDefaultBranch?: (repoRoot: string) => Promise<string>;
}): Promise<CreatePaseoWorktreeWorkflowResult>;
export declare function handleWorkspaceSetupStatusRequest(dependencies: HandleWorkspaceSetupStatusRequestDependencies, request: Extract<SessionInboundMessage, {
    type: "workspace_setup_status_request";
}>): Promise<void>;
export declare function handleWorkspaceSetupRunRequest(dependencies: HandleWorkspaceSetupRunRequestDependencies, request: Extract<SessionInboundMessage, {
    type: "workspace.setup.run.request";
}>): Promise<void>;
export declare function runWorktreeSetupInBackground(dependencies: CreatePaseoWorktreeInBackgroundDependencies, options: {
    requestCwd: string;
    repoRoot: string;
    workspaceId: string;
    worktree: WorktreeConfig;
    shouldBootstrap: boolean;
    slug: string;
    worktreePath: string;
    workspaceCwd?: string;
}, signal?: AbortSignal): Promise<void>;
export {};
//# sourceMappingURL=worktree-session.d.ts.map