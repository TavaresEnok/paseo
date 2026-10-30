import type { OutputSchema } from "../../output/index.js";
import { type ScheduleRow } from "./shared.js";
import type { ScheduleRecord, ScheduleRunRecord } from "./types.js";
export declare const scheduleSchema: OutputSchema<ScheduleRow>;
export interface ScheduleInspectRow {
    key: string;
    value: string;
}
export declare function createScheduleInspectSchema(record: ScheduleRecord): OutputSchema<ScheduleInspectRow>;
export interface ScheduleLogRow {
    id: string;
    status: string;
    startedAt: string;
    agentId: string | null;
    output: string | null;
    error: string | null;
}
export declare const scheduleLogSchema: OutputSchema<ScheduleLogRow>;
export declare function toScheduleLogRow(run: ScheduleRunRecord): ScheduleLogRow;
export declare function createScheduleInspectRows(schedule: ScheduleRecord): ScheduleInspectRow[];
//# sourceMappingURL=schema.d.ts.map