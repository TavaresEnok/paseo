import { scheduleSchema } from "./schema.js";
import { connectScheduleClient, requireNewAgentSchedule, toScheduleCommandError, toScheduleRow, } from "./shared.js";
export async function runPauseCommand(id, options, _command) {
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        await requireNewAgentSchedule(client, id);
        const payload = await client.schedulePause({ id });
        if (payload.error || !payload.schedule) {
            throw new Error(payload.error ?? `Failed to pause schedule: ${id}`);
        }
        return {
            type: "single",
            data: toScheduleRow(payload.schedule),
            schema: scheduleSchema,
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_PAUSE_FAILED", "pause schedule", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=pause.js.map