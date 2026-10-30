import type { Logger } from "pino";
import type { ProcessEnvRecord } from "../server/paseo-env.js";
import { type GitCommandRuntimeMetricsSnapshot } from "./git-command-runtime-metrics.js";
import { type GitProcessPriority, type GitProcessPolicy } from "./git-process-scheduler.js";
export declare function runWithGitCommandPriority<T>(priority: GitProcessPriority, operation: () => T): T;
export declare function configureGitProcessPolicy(policy: GitProcessPolicy): void;
export interface GitCommandOptions {
    cwd: string;
    input?: string | Buffer;
    env?: ProcessEnvRecord;
    envOverlay?: ProcessEnvRecord;
    logger?: Pick<Logger, "trace">;
    timeout?: number;
    maxOutputBytes?: number;
    acceptExitCodes?: number[];
}
export interface GitCommandResult<Output = string> {
    stdout: Output;
    stderr: string;
    truncated: boolean;
    exitCode: number | null;
    signal: NodeJS.Signals | null;
}
export type RunGitCommand = (args: string[], options: GitCommandOptions) => Promise<GitCommandResult>;
export declare function createRunGitCommand(provenance: string): RunGitCommand;
export interface GitCommandMetric {
    args: string[];
    cwd: string;
    startedAtMs: number;
    durationMs: number;
    exitCode: number | null;
    signal: NodeJS.Signals | null;
    success: boolean;
}
export interface GitCommandMetricsSnapshot {
    commands: GitCommandMetric[];
    submissions: GitCommandSubmissionMetric[];
    submitted: number;
    started: number;
    completed: number;
    active: number;
    pending: number;
    total: number;
    failed: number;
    maxConcurrent: number;
}
export interface GitCommandSubmissionMetric {
    args: string[];
    cwd: string;
}
export declare function startGitCommandMetrics(): void;
export declare function stopGitCommandMetrics(): GitCommandMetricsSnapshot;
export declare function getGitCommandMetrics(): GitCommandMetricsSnapshot;
export declare function waitForGitCommandMetricsIdle(options: {
    quietMs: number;
    timeoutMs: number;
}): Promise<void>;
export declare function snapshotGitCommandRuntimeMetrics(): GitCommandRuntimeMetricsSnapshot;
/** Binary stdout preserves cat-file byte framing before text decoding. */
export declare function runGitCommandBytes(args: string[], options: GitCommandOptions): Promise<GitCommandResult<Buffer>>;
export declare const runGitCommand: RunGitCommand;
//# sourceMappingURL=run-git-command.d.ts.map