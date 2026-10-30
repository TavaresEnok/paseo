export interface GitProcessPolicy {
    maxProcessesPerSecond: number;
    maxProcessConcurrency: number;
}
export declare const DEFAULT_GIT_PROCESS_POLICY: GitProcessPolicy;
export interface ScheduledGitProcess<T> {
    result: Promise<T>;
    exited: Promise<void>;
}
export type GitProcessPriority = "normal" | "high";
export declare function resolveGitProcessPolicy(input: {
    env: NodeJS.ProcessEnv;
    persisted?: Partial<GitProcessPolicy>;
}): GitProcessPolicy;
export declare class GitProcessScheduler {
    readonly policy: GitProcessPolicy;
    private readonly startThrottled;
    private readonly highPriorityQueue;
    private readonly normalPriorityQueue;
    private admitted;
    private running;
    private waiting;
    private drainScheduled;
    constructor(policy: GitProcessPolicy);
    get activeCount(): number;
    get pendingCount(): number;
    run<T>(start: () => ScheduledGitProcess<T>, options?: {
        priority?: GitProcessPriority;
    }): Promise<T>;
    private scheduleDrain;
    private drainOne;
    private execute;
}
//# sourceMappingURL=git-process-scheduler.d.ts.map