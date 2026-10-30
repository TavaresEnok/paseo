import { scheduleSchema } from "./schema.js";
import { connectScheduleClient, toScheduleCommandError, toScheduleRow, } from "./shared.js";
export async function runLsCommand(options, _command) {
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        const payload = await client.scheduleList();
        if (payload.error) {
            throw new Error(payload.error);
        }
        return {
            type: "list",
            data: payload.schedules
                .filter((schedule) => schedule.target.type === "new-agent")
                .map(toScheduleRow),
            schema: scheduleSchema,
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_LIST_FAILED", "list schedules", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=ls.js.map