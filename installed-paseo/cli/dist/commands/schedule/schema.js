import { formatCadence, formatTarget } from "./shared.js";
export const scheduleSchema = {
    idField: "id",
    columns: [
        { header: "ID", field: "id", width: 10 },
        { header: "NAME", field: "name", width: 20 },
        { header: "CADENCE", field: "cadence", width: 20 },
        { header: "TARGET", field: "target", width: 20 },
        { header: "STATUS", field: "status", width: 12 },
        { header: "NEXT RUN", field: "nextRunAt", width: 24 },
    ],
};
export function createScheduleInspectSchema(record) {
    return {
        idField: "key",
        columns: [
            { header: "KEY", field: "key", width: 18 },
            { header: "VALUE", field: "value", width: 80 },
        ],
        serialize: () => record,
    };
}
export const scheduleLogSchema = {
    idField: "id",
    columns: [
        { header: "RUN ID", field: "id", width: 14 },
        { header: "STATUS", field: "status", width: 12 },
        { header: "STARTED", field: "startedAt", width: 24 },
        { header: "AGENT", field: "agentId", width: 12 },
        { header: "OUTPUT", field: "output", width: 40 },
        { header: "ERROR", field: "error", width: 40 },
    ],
};
export function toScheduleLogRow(run) {
    return {
        id: run.id,
        status: run.status,
        startedAt: run.startedAt,
        agentId: run.agentId ? run.agentId.slice(0, 7) : null,
        output: run.output,
        error: run.error,
    };
}
export function createScheduleInspectRows(schedule) {
    return [
        { key: "Id", value: schedule.id },
        { key: "Name", value: schedule.name ?? "null" },
        { key: "Prompt", value: schedule.prompt },
        {
            key: "Cadence",
            value: schedule.cadence.type === "cron"
                ? formatCadence(schedule.cadence)
                : `every:${schedule.cadence.everyMs}ms`,
        },
        { key: "Target", value: formatTarget(schedule.target) },
        { key: "Status", value: schedule.status },
        { key: "CreatedAt", value: schedule.createdAt },
        { key: "UpdatedAt", value: schedule.updatedAt },
        { key: "NextRunAt", value: schedule.nextRunAt ?? "null" },
        { key: "LastRunAt", value: schedule.lastRunAt ?? "null" },
        { key: "PausedAt", value: schedule.pausedAt ?? "null" },
        { key: "ExpiresAt", value: schedule.expiresAt ?? "null" },
        { key: "MaxRuns", value: schedule.maxRuns == null ? "null" : `${schedule.maxRuns}` },
        { key: "RunCount", value: `${schedule.runs.length}` },
    ];
}
//# sourceMappingURL=schema.js.map