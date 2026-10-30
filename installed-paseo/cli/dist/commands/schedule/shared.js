import { connectToDaemon, getDaemonHost } from "../../utils/client.js";
import { parseDuration } from "../../utils/duration.js";
import { resolveProviderAndModel } from "../../utils/provider-model.js";
import { everyMsToFiveFieldCron } from "@getpaseo/protocol/schedule/cadence";
export async function connectScheduleClient(target) {
    const resolvedHost = getDaemonHost({ target });
    try {
        const client = (await connectToDaemon({
            target,
        }));
        return { client, host: resolvedHost };
    }
    catch (error) {
        if (error && typeof error === "object" && "code" in error)
            throw error;
        const message = error instanceof Error ? error.message : String(error);
        throw {
            code: "DAEMON_NOT_RUNNING",
            message: `Cannot connect to daemon at ${resolvedHost}: ${message}`,
            details: "Start the daemon with: paseo daemon start",
        };
    }
}
export function toScheduleCommandError(code, action, error) {
    if (error && typeof error === "object" && "code" in error) {
        return error;
    }
    const message = error instanceof Error ? error.message : String(error);
    return {
        code,
        message: `Failed to ${action}: ${message}`,
    };
}
export async function requireNewAgentSchedule(client, id) {
    const payload = await client.scheduleInspect({ id });
    if (payload.error || !payload.schedule || payload.schedule.target.type !== "new-agent") {
        throw new Error(payload.error ?? `Schedule not found: ${id}`);
    }
}
export function formatCadence(cadence) {
    if (cadence.type === "cron") {
        const timezoneSuffix = cadence.timezone ? ` (${cadence.timezone})` : "";
        return `cron:${cadence.expression}${timezoneSuffix}`;
    }
    return `every:${formatDurationMs(cadence.everyMs)}`;
}
export function formatTarget(target) {
    if (target.type === "self") {
        return `self:${target.agentId.slice(0, 7)}`;
    }
    if (target.type === "agent") {
        return `agent:${target.agentId.slice(0, 7)}`;
    }
    const modelSuffix = target.config.model ? `/${target.config.model}` : "";
    return `new-agent:${target.config.provider}${modelSuffix}`;
}
export function formatDurationMs(durationMs) {
    const parts = [];
    let remainingMs = durationMs;
    const hours = Math.floor(remainingMs / (60 * 60 * 1000));
    if (hours > 0) {
        parts.push(`${hours}h`);
        remainingMs -= hours * 60 * 60 * 1000;
    }
    const minutes = Math.floor(remainingMs / (60 * 1000));
    if (minutes > 0) {
        parts.push(`${minutes}m`);
        remainingMs -= minutes * 60 * 1000;
    }
    const seconds = Math.floor(remainingMs / 1000);
    if (seconds > 0 || parts.length === 0) {
        parts.push(`${seconds}s`);
    }
    return parts.join("");
}
function resolveScheduleTarget(args) {
    const { targetValue, hasExplicitNewAgentOption, createNewAgentTarget } = args;
    if (!targetValue) {
        return createNewAgentTarget();
    }
    if (targetValue === "new-agent") {
        return createNewAgentTarget();
    }
    if (hasExplicitNewAgentOption) {
        throw {
            code: "INVALID_TARGET",
            message: "--provider/--mode/--thinking can only be used with a new-agent target",
            details: "Use --target new-agent or omit --target to create a new agent schedule",
        };
    }
    if (targetValue === "self") {
        // COMPAT(scheduleSelfTarget): heartbeat creation moved to `paseo heartbeat create`.
        // Added in v0.2.0; remove after 2027-01-17.
        const currentAgentId = process.env.PASEO_AGENT_ID?.trim();
        if (!currentAgentId) {
            throw {
                code: "INVALID_TARGET",
                message: "--target self requires running inside a Paseo agent",
            };
        }
        return { type: "self", agentId: currentAgentId };
    }
    return { type: "agent", agentId: targetValue };
}
export function parseScheduleCreateInput(options) {
    const prompt = options.prompt.trim();
    if (!prompt) {
        throw {
            code: "INVALID_PROMPT",
            message: "Schedule prompt cannot be empty",
        };
    }
    const cadence = parseCadenceFromFlags(options.every, options.cron, options.timezone);
    if (!cadence) {
        throw {
            code: "INVALID_CADENCE",
            message: "Specify exactly one of --every or --cron",
        };
    }
    const cwdInput = options.cwd?.trim();
    if (options.daemonTarget.kind === "endpoint" && !cwdInput) {
        throw {
            code: "MISSING_CWD",
            message: "--cwd is required when --host is specified (the local working directory will not exist on the remote daemon)",
        };
    }
    const runOnCreate = resolveRunOnCreate(options.runNow, cadence.type);
    const targetValue = options.target?.trim();
    const modeId = options.mode?.trim();
    const thinkingOptionId = options.thinking?.trim();
    if (options.thinking !== undefined && !thinkingOptionId) {
        throw {
            code: "INVALID_THINKING_OPTION",
            message: "--thinking cannot be empty",
        };
    }
    const hasExplicitNewAgentOption = options.provider !== undefined || options.mode !== undefined || options.thinking !== undefined;
    const createNewAgentTarget = () => {
        const resolvedProviderModel = resolveProviderAndModel({
            provider: options.provider,
        });
        return {
            type: "new-agent",
            config: {
                provider: resolvedProviderModel.provider,
                cwd: cwdInput ?? process.cwd(),
                ...(resolvedProviderModel.model ? { model: resolvedProviderModel.model } : {}),
                ...(modeId ? { modeId } : {}),
                ...(thinkingOptionId ? { thinkingOptionId } : {}),
            },
        };
    };
    const target = resolveScheduleTarget({
        targetValue,
        hasExplicitNewAgentOption,
        createNewAgentTarget,
    });
    const maxRuns = options.maxRuns === undefined ? undefined : parsePositiveInt(options.maxRuns, "--max-runs");
    const expiresAt = options.expiresIn === undefined
        ? undefined
        : new Date(Date.now() + parseDuration(options.expiresIn)).toISOString();
    return {
        prompt,
        cadence,
        target,
        runOnCreate,
        ...(options.name?.trim() ? { name: options.name.trim() } : {}),
        ...(maxRuns !== undefined ? { maxRuns } : {}),
        ...(expiresAt ? { expiresAt } : {}),
    };
}
function resolveRunOnCreate(runNow, _cadenceType) {
    return runNow ?? false;
}
export function parseScheduleUpdateInput(options) {
    const id = options.id.trim();
    if (!id) {
        throw {
            code: "INVALID_SCHEDULE_ID",
            message: "Schedule id cannot be empty",
        };
    }
    const cadence = parseCadenceFromFlags(options.every, options.cron, options.timezone);
    const newAgentConfig = buildNewAgentConfigPatch(options);
    const maxRuns = parseUpdateMaxRuns(options);
    const expiresAt = parseUpdateExpiresAt(options);
    const name = parseUpdateName(options);
    const prompt = parseUpdatePrompt(options);
    if (name === undefined &&
        prompt === undefined &&
        cadence === undefined &&
        newAgentConfig === undefined &&
        maxRuns === undefined &&
        expiresAt === undefined) {
        throw {
            code: "NO_UPDATES",
            message: "Specify at least one field to update",
        };
    }
    return {
        id,
        ...(name !== undefined ? { name } : {}),
        ...(prompt !== undefined ? { prompt } : {}),
        ...(cadence !== undefined ? { cadence } : {}),
        ...(newAgentConfig !== undefined ? { newAgentConfig } : {}),
        ...(maxRuns !== undefined ? { maxRuns } : {}),
        ...(expiresAt !== undefined ? { expiresAt } : {}),
    };
}
function parseCadenceFromFlags(every, cron, timezone) {
    if (every !== undefined && cron !== undefined) {
        throw {
            code: "INVALID_CADENCE",
            message: "Specify at most one of --every or --cron",
        };
    }
    const trimmedTimeZone = parseTimeZoneFlag(timezone);
    if (trimmedTimeZone !== undefined && cron === undefined) {
        throw {
            code: "INVALID_TIME_ZONE",
            message: "--timezone can only be used with --cron",
        };
    }
    if (every !== undefined) {
        return { type: "cron", expression: compileEveryPresetToCron(every) };
    }
    if (cron !== undefined) {
        return {
            type: "cron",
            expression: cron.trim(),
            ...(trimmedTimeZone ? { timezone: trimmedTimeZone } : {}),
        };
    }
    return undefined;
}
export function compileEveryPresetToCron(value) {
    const durationMs = parseDuration(value);
    const cron = everyMsToFiveFieldCron(durationMs);
    if (cron) {
        return cron;
    }
    throw {
        code: "UNREPRESENTABLE_CADENCE",
        message: `${value} cannot be represented faithfully by five-field cron`,
        details: "Use --cron for calendar schedules",
    };
}
function parseTimeZoneFlag(timeZone) {
    if (timeZone === undefined) {
        return undefined;
    }
    const trimmed = timeZone.trim();
    if (!trimmed) {
        throw {
            code: "INVALID_TIME_ZONE",
            message: "--timezone cannot be empty",
        };
    }
    return trimmed;
}
function parseUpdateMaxRuns(options) {
    if (options.maxRuns !== undefined && options.clearMaxRuns) {
        throw {
            code: "CONFLICTING_MAX_RUNS",
            message: "Use either --max-runs <n> or --no-max-runs, not both",
        };
    }
    if (options.clearMaxRuns) {
        return null;
    }
    if (options.maxRuns !== undefined) {
        return parsePositiveInt(options.maxRuns, "--max-runs");
    }
    return undefined;
}
function parseUpdateExpiresAt(options) {
    if (options.expiresIn !== undefined && options.clearExpires) {
        throw {
            code: "CONFLICTING_EXPIRES",
            message: "Use either --expires-in <duration> or --no-expires-in, not both",
        };
    }
    if (options.clearExpires) {
        return null;
    }
    if (options.expiresIn !== undefined) {
        return new Date(Date.now() + parseDuration(options.expiresIn)).toISOString();
    }
    return undefined;
}
function parseUpdateName(options) {
    if (options.name === undefined) {
        return undefined;
    }
    const trimmed = options.name.trim();
    return trimmed.length > 0 ? trimmed : null;
}
function parseUpdatePrompt(options) {
    if (options.prompt === undefined) {
        return undefined;
    }
    const trimmed = options.prompt.trim();
    if (!trimmed) {
        throw {
            code: "INVALID_PROMPT",
            message: "--prompt cannot be empty",
        };
    }
    return trimmed;
}
function buildNewAgentConfigPatch(options) {
    const patch = {};
    if (options.provider !== undefined || options.model !== undefined) {
        const resolved = resolveProviderAndModel({
            provider: options.provider,
            model: options.model,
        });
        patch.provider = resolved.provider;
        if (resolved.model !== undefined) {
            patch.model = resolved.model;
        }
    }
    if (options.mode !== undefined) {
        const trimmed = options.mode.trim();
        patch.modeId = trimmed.length > 0 ? trimmed : null;
    }
    if (options.cwd !== undefined) {
        const trimmed = options.cwd.trim();
        if (!trimmed) {
            throw {
                code: "INVALID_CWD",
                message: "--cwd cannot be empty",
            };
        }
        patch.cwd = trimmed;
    }
    return Object.keys(patch).length > 0 ? patch : undefined;
}
function parsePositiveInt(value, flag) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isInteger(parsed) || parsed <= 0) {
        throw {
            code: "INVALID_INTEGER",
            message: `${flag} must be a positive integer`,
        };
    }
    return parsed;
}
export function toScheduleRow(schedule) {
    return {
        id: schedule.id,
        name: schedule.name,
        cadence: formatCadence(schedule.cadence),
        target: formatTarget(schedule.target),
        status: schedule.status,
        nextRunAt: schedule.nextRunAt,
        lastRunAt: schedule.lastRunAt,
    };
}
//# sourceMappingURL=shared.js.map