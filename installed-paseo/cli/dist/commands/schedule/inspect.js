import { createScheduleInspectRows, createScheduleInspectSchema, } from "./schema.js";
import { connectScheduleClient, toScheduleCommandError, } from "./shared.js";
export async function runInspectCommand(id, options, _command) {
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        const payload = await client.scheduleInspect({ id });
        if (payload.error || !payload.schedule) {
            throw new Error(payload.error ?? `Schedule not found: ${id}`);
        }
        if (payload.schedule.target.type !== "new-agent") {
            throw new Error(`Schedule not found: ${id}`);
        }
        const rows = createScheduleInspectRows(payload.schedule);
        return {
            type: "list",
            data: rows,
            schema: createScheduleInspectSchema(payload.schedule),
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_INSPECT_FAILED", "inspect schedule", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=inspect.js.map