import { Command } from "commander";
import { DaemonConnectionError } from "@getpaseo/client/internal/daemon-client";
import { readDaemonInstance, daemonLogPath, isSameDaemonInstance, DaemonInstanceError, } from "@getpaseo/server/daemon-control";
import { readPersistedConfig, resolveConfigFromPersisted } from "@getpaseo/server/configuration";
import { connectToDaemon, buildDaemonConnectionCommandError } from "../../utils/client.js";
import { withOutput, toCommandError } from "../../output/index.js";
import { addJsonAndDaemonHostOptions } from "../../utils/command-options.js";
import { describeDaemonTarget } from "../../utils/daemon-target.js";
export function daemonStatusCommand() {
    return addJsonAndDaemonHostOptions(new Command("status").description("Observe the selected daemon and its published endpoint")).action(withOutput(runStatusCommand));
}
export async function runStatusCommand(options, _command) {
    const target = options.daemonTarget;
    const instance = target.kind === "instance" ? await readDaemonInstance(target.home) : null;
    const local = target.kind === "instance"
        ? localStatus(target.home, instance)
        : { host: describeDaemonTarget(target) };
    const observed = target.kind === "endpoint" || instance?.listen
        ? await probeDaemonStatus(target, instance, local)
        : { connectedDaemon: "not_probed" };
    const data = { ...local, ...observed };
    return {
        type: "single",
        data,
        schema: {
            idField: () => "daemon",
            columns: [],
            renderHuman: () => Object.entries(data)
                .filter(([, value]) => value !== undefined)
                .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`)
                .join("\n"),
        },
    };
}
async function probeDaemonStatus(target, instance, local) {
    let connectedDaemon = "unreachable";
    let note;
    let live = {};
    let client;
    try {
        client = await connectToDaemon({ target, instance: instance ?? undefined, timeout: 1500 });
    }
    catch (error) {
        const failure = buildDaemonConnectionCommandError({ target, error });
        if (target.kind === "endpoint")
            throw failure;
        connectedDaemon = "unreachable";
        if (failure.code === "AUTH_REQUIRED")
            connectedDaemon = "auth_required";
        if (failure.code === "AUTH_FAILED")
            connectedDaemon = "auth_failed";
        note = failure.message;
    }
    if (!client)
        return { connectedDaemon, note };
    try {
        let requestError;
        const status = await client.getDaemonStatus({ timeout: 1500 }).catch((error) => {
            requestError = error;
            return null;
        });
        // Recheck even when the RPC times out before combining local and live observations.
        const current = target.kind === "instance" ? await readDaemonInstance(target.home) : null;
        if (instance && (!current || !isSameDaemonInstance(instance, current)))
            throw new DaemonInstanceError("DAEMON_REPLACED", "Supervisor exited or was replaced during status observation.");
        const info = client.getLastServerInfoMessage();
        live = { serverId: info?.serverId, daemonVersion: info?.version };
        connectedDaemon = client.isConnected ? "reachable" : "unreachable";
        if (!status) {
            const failure = toCommandError(requestError);
            note = `Status details unavailable (${failure.code}): ${failure.message}`;
            if (target.kind === "endpoint" ||
                !client.isConnected ||
                !(requestError instanceof DaemonConnectionError) ||
                requestError.code !== "DAEMON_REQUEST_TIMEOUT") {
                throw { ...failure, message: note, details: { ...local, ...live, connectedDaemon } };
            }
        }
        else {
            live = {
                ...live,
                daemonVersion: status.version,
                workerPid: status.pid,
                daemonNode: status.nodePath,
                providers: status.providers,
                relay: status.relay,
            };
        }
    }
    finally {
        await client.close();
    }
    return { ...live, connectedDaemon, note };
}
function localStatus(home, instance) {
    const config = resolveConfigFromPersisted(home, readPersistedConfig(home, { defaultsIfMissing: true }), { env: {} });
    let localDaemon = "stopped";
    if (instance)
        localDaemon = instance.listen ? "running" : "not_ready";
    return {
        home,
        pid: instance?.pid ?? null,
        startedAt: instance?.startedAt ?? null,
        listen: instance?.listen ?? null,
        serverId: instance?.serverId ?? undefined,
        hostname: instance?.hostname ?? null,
        configuredListen: config.listen,
        localDaemon,
        desktopManaged: instance?.desktopManaged === true,
        logPath: daemonLogPath(home),
    };
}
//# sourceMappingURL=status.js.map