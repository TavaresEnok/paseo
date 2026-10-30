import { scheduleSchema } from "./schema.js";
import { connectScheduleClient, parseScheduleCreateInput, toScheduleCommandError, toScheduleRow, } from "./shared.js";
export async function runCreateCommand(prompt, options, command) {
    const runNowSource = command.getOptionValueSource("runNow");
    const runNow = runNowSource === "cli" ? Boolean(options.runNow) : undefined;
    const input = parseScheduleCreateInput({
        prompt,
        every: options.every,
        cron: options.cron,
        timezone: options.timezone,
        name: options.name,
        target: options.target,
        provider: options.provider,
        mode: options.mode,
        thinking: options.thinking,
        cwd: options.cwd,
        daemonTarget: options.daemonTarget,
        maxRuns: options.maxRuns,
        expiresIn: options.expiresIn,
        runNow,
    });
    const { client } = await connectScheduleClient(options.daemonTarget);
    try {
        const payload = await client.scheduleCreate(input);
        if (payload.error || !payload.schedule) {
            throw new Error(payload.error ?? "Schedule creation failed");
        }
        return {
            type: "single",
            data: toScheduleRow(payload.schedule),
            schema: scheduleSchema,
        };
    }
    catch (error) {
        throw toScheduleCommandError("SCHEDULE_CREATE_FAILED", "create schedule", error);
    }
    finally {
        await client.close().catch(() => { });
    }
}
//# sourceMappingURL=create.js.map