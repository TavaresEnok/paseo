import { createHostClient, parseHostTarget } from "@getpaseo/client/node";
import { waitForDaemonReady, resolvePaseoHome, readLocalCredentialForTarget, } from "@getpaseo/server/daemon-control";
import { describeDaemonTarget } from "./daemon-target.js";
import { buildDaemonWebSocketUrl, normalizeHostPort, parseConnectionUri, } from "@getpaseo/protocol/daemon-endpoints";
import { getOrCreateCliClientId } from "./client-id.js";
import { resolveCliVersion } from "../version.js";
export function resolveClientPaseoHome(target, env = process.env) {
    return target.kind === "instance" ? target.home : resolvePaseoHome(env);
}
const DEFAULT_TIMEOUT = 15000;
export function getDaemonHost(options) {
    return describeDaemonTarget(options.target);
}
export function buildDaemonConnectionCommandError(options) {
    const error = options.error;
    let message = error instanceof Error ? error.message : String(error);
    if (error && typeof error === "object" && "message" in error)
        message = String(error.message);
    if (options.target.kind === "endpoint")
        message = message.replaceAll(options.target.host, describeDaemonTarget(options.target));
    let code = "DAEMON_UNREACHABLE";
    if (typeof error === "object" && error !== null && "code" in error)
        code = String(error.code);
    else if (message === "Password required")
        code = "AUTH_REQUIRED";
    else if (message === "Incorrect password")
        code = "AUTH_FAILED";
    return {
        code,
        message: message.startsWith("Cannot connect to daemon at ")
            ? message
            : `Cannot connect to daemon at ${describeDaemonTarget(options.target)}: ${message}`,
        details: describeConnectionRemedy(code, options.target),
    };
}
function describeConnectionRemedy(code, target) {
    if (code === "AUTH_REQUIRED")
        return "The daemon requires a password. Set PASEO_PASSWORD and retry.";
    if (code === "AUTH_FAILED")
        return "The daemon rejected the password. Check PASEO_PASSWORD and retry.";
    if (target.kind === "instance")
        return `Start with: paseo daemon start --home ${JSON.stringify(target.home)}`;
    return "Check the selected endpoint and credentials. SSH transport does not install or start the daemon.";
}
export function normalizeDaemonHost(raw) {
    const trimmed = raw.trim();
    if (!trimmed) {
        return null;
    }
    if (trimmed.startsWith("tcp://")) {
        try {
            const parsed = parseConnectionUri(trimmed);
            const endpoint = normalizeHostPort(parsed.isIpv6 ? `[${parsed.host}]:${parsed.port}` : `${parsed.host}:${parsed.port}`);
            const query = new URLSearchParams();
            if (parsed.useTls) {
                query.set("ssl", "true");
            }
            if (parsed.password) {
                query.set("password", parsed.password);
            }
            const queryString = query.toString();
            const suffix = queryString ? `?${queryString}` : "";
            return `tcp://${endpoint}${suffix}`;
        }
        catch {
            return null;
        }
    }
    if (trimmed.startsWith("unix://") ||
        trimmed.startsWith("pipe://") ||
        trimmed.startsWith("\\\\.\\pipe\\")) {
        return trimmed.startsWith("\\\\.\\pipe\\") ? `pipe://${trimmed}` : trimmed;
    }
    if (trimmed.startsWith("/") || trimmed.startsWith("~")) {
        return `unix://${trimmed}`;
    }
    // Windows absolute paths (e.g. C:\Users\foo) are filesystem paths, not TCP or IPC targets.
    if (/^[A-Za-z]:[/\\]/.test(trimmed)) {
        return null;
    }
    if (/^\d+$/.test(trimmed)) {
        return `127.0.0.1:${trimmed}`;
    }
    return trimmed.includes(":") ? trimmed : null;
}
function stripIpcPrefix(trimmed) {
    if (trimmed.startsWith("unix://"))
        return trimmed.slice("unix://".length).trim();
    if (trimmed.startsWith("pipe://"))
        return trimmed.slice("pipe://".length).trim();
    return trimmed;
}
export function resolveDaemonTarget(host) {
    const trimmed = normalizeDaemonHost(host);
    if (!trimmed) {
        throw new Error(`Invalid daemon target: ${host}`);
    }
    if (trimmed.startsWith("unix://") ||
        trimmed.startsWith("pipe://") ||
        trimmed.startsWith("\\\\.\\pipe\\")) {
        const socketPath = stripIpcPrefix(trimmed);
        if (!socketPath) {
            throw new Error("Invalid IPC daemon target: missing socket path");
        }
        const isUnixSocket = trimmed.startsWith("unix://");
        return {
            type: "ipc",
            url: isUnixSocket ? `ws+unix://${socketPath}:/ws` : "ws://localhost/ws",
            socketPath,
        };
    }
    if (trimmed.startsWith("tcp://")) {
        const parsed = parseConnectionUri(trimmed);
        const endpoint = normalizeHostPort(parsed.isIpv6 ? `[${parsed.host}]:${parsed.port}` : `${parsed.host}:${parsed.port}`);
        return {
            type: "tcp",
            url: buildDaemonWebSocketUrl(endpoint, { useTls: parsed.useTls }),
        };
    }
    return {
        type: "tcp",
        url: `ws://${trimmed}/ws`,
    };
}
export function resolveDaemonPassword(host) {
    const fromUri = parseHostTarget(host).password;
    if (fromUri)
        return fromUri;
    const fromEnv = process.env.PASEO_PASSWORD;
    return fromEnv && fromEnv.length > 0 ? fromEnv : undefined;
}
export function resolveDaemonCredential(host, home) {
    const password = resolveDaemonPassword(host);
    if (password)
        return { kind: "password", password };
    const token = readLocalCredentialForTarget(home, host);
    return token ? { kind: "localCredential", token } : null;
}
async function connectSelectedDaemon(options) {
    const timeout = options.timeout ?? DEFAULT_TIMEOUT;
    const host = options.target.kind === "endpoint"
        ? options.target.host
        : (await waitForDaemonReady(options.target.home, {
            timeoutMs: timeout,
            instance: options.instance,
        })).listen;
    const home = resolveClientPaseoHome(options.target);
    const credential = resolveDaemonCredential(host, home);
    const client = createHostClient(host, {
        clientId: await getOrCreateCliClientId(home),
        clientType: "cli",
        appVersion: resolveCliVersion(),
        ...(credential?.kind === "password" ? { password: credential.password } : {}),
        ...(credential?.kind === "localCredential"
            ? { localCredential: () => readLocalCredentialForTarget(home, host) ?? undefined }
            : {}),
        connectTimeoutMs: timeout,
        reconnect: { enabled: false },
    });
    try {
        await client.connect();
        return client;
    }
    catch (error) {
        await client.close();
        throw error;
    }
}
export async function connectToDaemon(options) {
    try {
        return await connectSelectedDaemon(options);
    }
    catch (error) {
        throw buildDaemonConnectionCommandError({ ...options, error });
    }
}
/**
 * Try to connect to the daemon, returns null if connection fails
 */
export async function tryConnectToDaemon(options) {
    try {
        return await connectToDaemon(options);
    }
    catch {
        return null;
    }
}
/**
 * Resolve an agent ID from a partial ID or name.
 * Supports:
 * - Full ID match
 * - Prefix match (first N characters)
 * - Title/name match (case-insensitive)
 *
 * Returns the full agent ID if found, null otherwise.
 */
export function resolveAgentId(idOrName, agents) {
    if (!idOrName || agents.length === 0) {
        return null;
    }
    const query = idOrName.toLowerCase();
    // Try exact ID match first
    const exactMatch = agents.find((a) => a.id === idOrName);
    if (exactMatch) {
        return exactMatch.id;
    }
    // Try ID prefix match
    const prefixMatches = agents.filter((a) => a.id.toLowerCase().startsWith(query));
    if (prefixMatches.length === 1 && prefixMatches[0]) {
        return prefixMatches[0].id;
    }
    // Try title/name match (case-insensitive)
    const titleMatches = agents.filter((a) => a.title?.toLowerCase() === query);
    if (titleMatches.length === 1 && titleMatches[0]) {
        return titleMatches[0].id;
    }
    // Try partial title match
    const partialTitleMatches = agents.filter((a) => a.title?.toLowerCase().includes(query));
    if (partialTitleMatches.length === 1 && partialTitleMatches[0]) {
        return partialTitleMatches[0].id;
    }
    // If we have multiple prefix matches and no unique title match, return first prefix match
    const firstPrefixMatch = prefixMatches[0];
    if (firstPrefixMatch) {
        return firstPrefixMatch.id;
    }
    return null;
}
//# sourceMappingURL=client.js.map