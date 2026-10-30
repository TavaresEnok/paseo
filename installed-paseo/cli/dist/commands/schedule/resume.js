import { scheduleSchema } from "./schema.js";
import { connectScheduleClient, requireNewAgentSchedule, toScheduleCommandError, toScheduleRow, } from "./shared.js";
export async function runResumeCommand(id, options, _command) {
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        await requireNewAgentSchedule(client, id);
        const payload = await client.scheduleResume({ id });
        if (payload.error || !payload.schedule) {
            throw new Error(payload.error ?? `Failed to resume schedule: ${id}`);
        }
        return {
            type: "single",
            data: toScheduleRow(payload.schedule),
            schema: scheduleSchema,
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_RESUME_FAILED", "resume schedule", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=resume.js.map