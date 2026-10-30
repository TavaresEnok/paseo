import { createScheduleInspectRows, createScheduleInspectSchema, } from "./schema.js";
import { connectScheduleClient, parseScheduleUpdateInput, requireNewAgentSchedule, toScheduleCommandError, } from "./shared.js";
export async function runUpdateCommand(id, options, _command) {
    const input = parseScheduleUpdateInput({
        id,
        every: options.every,
        cron: options.cron,
        timezone: options.timezone,
        name: options.name,
        prompt: options.prompt,
        provider: options.provider,
        model: options.model,
        mode: options.mode,
        cwd: options.cwd,
        maxRuns: options.maxRuns === false ? undefined : options.maxRuns,
        expiresIn: options.expiresIn === false ? undefined : options.expiresIn,
        clearMaxRuns: options.maxRuns === false,
        clearExpires: options.expiresIn === false,
    });
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        await requireNewAgentSchedule(client, id);
        const payload = await client.scheduleUpdate(input);
        if (payload.error || !payload.schedule) {
            throw new Error(payload.error ?? `Failed to update schedule: ${id}`);
        }
        return {
            type: "list",
            data: createScheduleInspectRows(payload.schedule),
            schema: createScheduleInspectSchema(payload.schedule),
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_UPDATE_FAILED", "update schedule", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=update.js.map