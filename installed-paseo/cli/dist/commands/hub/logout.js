import { confirm, isCancel } from "@clack/prompts";
import { withOutput } from "../../output/index.js";
import { addJsonAndDaemonHostOptions } from "../../utils/command-options.js";
import { withHubDaemon } from "./daemon-client.js";
import { reportHubProgress } from "./reporter.js";
const schema = {
    idField: "status",
    columns: [
        { header: "HUB", field: "origin" },
        { header: "STATUS", field: "status" },
        { header: "DAEMON DISCONNECTED", field: "daemonDisconnected" },
        { header: "WARNING", field: "warning" },
    ],
};
export async function runHubLogout(options, dependencies) {
    const active = dependencies.credentials.active();
    if (active === null) {
        return logoutResult({ origin: null, status: "not_logged_in", daemonDisconnected: false });
    }
    reportHubProgress(dependencies.reporter, options, `Logging out of ${active.origin}`);
    const mayPrompt = options.json !== true && dependencies.isInteractive();
    let daemonStatus = null;
    const shouldInspectDaemon = options.disconnectDaemon === true || mayPrompt;
    if (shouldInspectDaemon) {
        daemonStatus = await withHubDaemon(dependencies.daemon, options.daemonTarget, async (daemon) => daemon.getHubStatus().then((response) => response.status));
    }
    const sameHub = daemonStatus?.hubOrigin === active.origin;
    let shouldDisconnect = options.disconnectDaemon === true && sameHub;
    if (options.disconnectDaemon !== true && mayPrompt && sameHub) {
        shouldDisconnect = await dependencies.confirmDisconnect(active.origin);
    }
    if (!shouldDisconnect) {
        dependencies.credentials.logoutActive();
        return logoutResult({ origin: active.origin, status: "logged_out", daemonDisconnected: false });
    }
    reportHubProgress(dependencies.reporter, options, `Disconnecting this daemon from ${active.origin}`);
    const disconnect = await withHubDaemon(dependencies.daemon, options.daemonTarget, async (daemon) => {
        return daemon.disconnectHub(options.force ?? false);
    });
    dependencies.credentials.logoutActive();
    return logoutResult({
        origin: active.origin,
        status: "logged_out",
        daemonDisconnected: disconnect.status.state === "not_connected",
        ...(disconnect.warning ? { warning: disconnect.warning } : {}),
    });
}
export function addHubLogoutCommand(parent, dependencies) {
    addJsonAndDaemonHostOptions(parent
        .command("logout")
        .description("Remove the active stored Hub CLI login")
        .option("--disconnect-daemon", "Also disconnect a daemon related to the same Hub")
        .option("--force", "Remove daemon authority without notifying the Hub")).action(withOutput(async (...args) => {
        const options = args.at(-2);
        return runHubLogout(options, dependencies);
    }));
}
export const productionLogoutPrompt = {
    isInteractive: () => Boolean(process.stdin.isTTY && process.stdout.isTTY),
    async confirmDisconnect(origin) {
        const answer = await confirm({
            message: `Disconnect this daemon from ${origin}?`,
            initialValue: false,
        });
        return !isCancel(answer) && answer;
    },
};
function logoutResult(data) {
    return { type: "single", data, schema };
}
//# sourceMappingURL=logout.js.map