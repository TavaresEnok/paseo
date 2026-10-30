import type { DaemonTarget } from "../../utils/daemon-target.js";
import type { CommandError, CommandOptions } from "../../output/index.js";
import type { CreateScheduleInput, ScheduleCadence, ScheduleDaemonClient, ScheduleListItem, ScheduleRecord, ScheduleTarget, UpdateScheduleInput } from "./types.js";
export interface ScheduleCommandOptions extends CommandOptions {
    host?: string;
}
export declare function connectScheduleClient(target: DaemonTarget): Promise<{
    client: ScheduleDaemonClient;
    host: string;
}>;
export declare function toScheduleCommandError(code: string, action: string, error: unknown): CommandError;
export declare function requireNewAgentSchedule(client: ScheduleDaemonClient, id: string): Promise<void>;
export declare function formatCadence(cadence: ScheduleCadence): string;
export declare function formatTarget(target: ScheduleTarget | ScheduleListItem["target"]): string;
export declare function formatDurationMs(durationMs: number): string;
export declare function parseScheduleCreateInput(options: {
    prompt: string;
    every?: string;
    cron?: string;
    timezone?: string;
    name?: string;
    target?: string;
    provider?: string;
    mode?: string;
    thinking?: string;
    cwd?: string;
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
    maxRuns?: string;
    expiresIn?: string;
    runNow?: boolean;
}): CreateScheduleInput;
export interface ScheduleUpdateOptionsInput {
    id: string;
    every?: string;
    cron?: string;
    timezone?: string;
    name?: string;
    prompt?: string;
    provider?: string;
    model?: string;
    mode?: string;
    cwd?: string;
    maxRuns?: string;
    expiresIn?: string;
    clearMaxRuns?: boolean;
    clearExpires?: boolean;
}
export declare function parseScheduleUpdateInput(options: ScheduleUpdateOptionsInput): UpdateScheduleInput;
export declare function compileEveryPresetToCron(value: string): string;
export interface ScheduleRow {
    id: string;
    name: string | null;
    cadence: string;
    target: string;
    status: string;
    nextRunAt: string | null;
    lastRunAt: string | null;
}
export declare function toScheduleRow(schedule: ScheduleListItem | ScheduleRecord): ScheduleRow;
//# sourceMappingURL=shared.d.ts.map