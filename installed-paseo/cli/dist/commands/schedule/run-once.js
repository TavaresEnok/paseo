import { scheduleSchema } from "./schema.js";
import { connectScheduleClient, requireNewAgentSchedule, toScheduleCommandError, toScheduleRow, } from "./shared.js";
export async function runRunOnceCommand(id, options, _command) {
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        await requireNewAgentSchedule(client, id);
        const payload = await client.scheduleRunOnce({ id });
        if (payload.error || !payload.schedule) {
            throw new Error(payload.error ?? `Failed to run schedule once: ${id}`);
        }
        return {
            type: "single",
            data: toScheduleRow(payload.schedule),
            schema: scheduleSchema,
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_RUN_ONCE_FAILED", "run schedule once", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=run-once.js.map