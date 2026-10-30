import { connectToDaemon } from "../../utils/client.js";
import { collectMultiple } from "../../utils/command-options.js";
import { agentRunSchema } from "./run.js";
export function addImportOptions(cmd) {
    return cmd
        .description("Import an existing provider session as a Paseo agent")
        .argument("<id>", "Provider session/thread ID to import")
        .requiredOption("--provider <provider>", "Agent provider id")
        .option("--cwd <path>", "Working directory for providers that require it")
        .option("--label <key=value>", "Add label(s) to the agent (can be used multiple times)", collectMultiple, []);
}
function toImportResult(agent) {
    return {
        agentId: agent.id,
        status: agent.status === "running" ? "running" : "created",
        provider: agent.provider,
        cwd: agent.cwd,
        title: agent.title,
    };
}
function parseImportProvider(provider) {
    const normalizedProvider = provider?.trim();
    if (!normalizedProvider) {
        throw {
            code: "MISSING_PROVIDER",
            message: "Provider is required",
            details: "Usage: paseo import --provider <provider> <id>",
        };
    }
    return normalizedProvider;
}
function parseImportLabels(labelFlags) {
    const labels = {};
    if (!labelFlags) {
        return labels;
    }
    for (const labelFlag of labelFlags) {
        const eqIndex = labelFlag.indexOf("=");
        if (eqIndex === -1) {
            throw {
                code: "INVALID_LABEL",
                message: `Invalid label format: ${labelFlag}`,
                details: "Labels must be in key=value format",
            };
        }
        const key = labelFlag.slice(0, eqIndex).trim();
        if (!key) {
            throw {
                code: "INVALID_LABEL",
                message: `Invalid label format: ${labelFlag}`,
                details: "Labels must include a non-empty key in key=value format",
            };
        }
        labels[key] = labelFlag.slice(eqIndex + 1);
    }
    return labels;
}
export function resolveImportCwd(explicitCwd, defaultCwd) {
    const cwd = explicitCwd?.trim() ?? defaultCwd;
    if (!cwd.trim()) {
        throw {
            code: "INVALID_CWD",
            message: "--cwd cannot be empty",
            details: "Provide a working directory path or omit --cwd",
        };
    }
    return cwd;
}
export async function runImportCommand(sessionIdArg, options, _command) {
    const sessionId = sessionIdArg.trim();
    if (!sessionId) {
        throw {
            code: "MISSING_SESSION_ID",
            message: "Session ID is required",
            details: "Usage: paseo import --provider <provider> <id>",
        };
    }
    const provider = parseImportProvider(options.provider);
    const cwd = resolveImportCwd(options.cwd, process.cwd());
    const labels = parseImportLabels(options.label);
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const agent = await client.importAgent({
            provider,
            sessionId,
            cwd,
            ...(Object.keys(labels).length > 0 ? { labels } : {}),
        });
        await client.close();
        return {
            type: "single",
            data: toImportResult(agent),
            schema: agentRunSchema,
        };
    }
    catch (err) {
        await client.close().catch(() => { });
        if (err && typeof err === "object" && "code" in err) {
            throw err;
        }
        const message = err instanceof Error ? err.message : String(err);
        throw {
            code: "AGENT_IMPORT_FAILED",
            message: `Failed to import agent: ${message}`,
        };
    }
}
//# sourceMappingURL=import.js.map