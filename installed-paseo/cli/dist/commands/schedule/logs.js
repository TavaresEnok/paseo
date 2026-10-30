import { scheduleLogSchema, toScheduleLogRow } from "./schema.js";
import { connectScheduleClient, requireNewAgentSchedule, toScheduleCommandError, } from "./shared.js";
export async function runLogsCommand(id, options, _command) {
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        await requireNewAgentSchedule(client, id);
        const payload = await client.scheduleLogs({ id });
        if (payload.error) {
            throw new Error(payload.error);
        }
        return {
            type: "list",
            data: payload.runs.map(toScheduleLogRow),
            schema: scheduleLogSchema,
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_LOGS_FAILED", "read schedule logs", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=logs.js.map