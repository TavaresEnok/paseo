import { connectScheduleClient, toScheduleCommandError, } from "./shared.js";
const scheduleDeleteSchema = {
    idField: "id",
    columns: [
        { header: "ID", field: "id", width: 10 },
        { header: "STATUS", field: "status", width: 12 },
    ],
};
export async function runDeleteCommand(id, options, _command) {
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        const payload = await client.scheduleDelete({ id });
        if (payload.error) {
            throw new Error(payload.error);
        }
        return {
            type: "single",
            data: {
                id: payload.scheduleId,
                status: "deleted",
            },
            schema: scheduleDeleteSchema,
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_DELETE_FAILED", "delete schedule", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=delete.js.map