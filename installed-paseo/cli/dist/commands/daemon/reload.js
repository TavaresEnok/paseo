import { addJsonAndDaemonHostOptions } from "../../utils/command-options.js";
import { withOutput } from "../../output/index.js";
import { Command } from "commander";
import { describeDaemonTarget } from "../../utils/daemon-target.js";
import { connectToDaemon } from "../../utils/client.js";
export const daemonReloadSchema = {
    idField: () => "daemon-config",
    columns: [],
    renderHuman(result) {
        if (result.type !== "single")
            return "";
        const lines = ["Configuration reloaded."];
        if (result.data.restartRequiredPaths.length > 0) {
            lines.push("", "Warning: These changes require a daemon restart:", ...result.data.restartRequiredPaths.map((path) => `  ${path}`), "", `Run: ${result.data.restartCommand}`);
        }
        if (result.data.overrideControlledPaths.length > 0) {
            lines.push("", "Warning: These settings are controlled by daemon launch overrides:", ...result.data.overrideControlledPaths.map((path) => `  ${path}`));
        }
        return lines.join("\n");
    },
};
export async function runDaemonReloadCommand(options, _command) {
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const payload = await client.reloadDaemonConfig();
        return {
            type: "single",
            data: {
                restartCommand: `paseo daemon restart ${options.daemonTarget.kind === "instance" ? `--home ${JSON.stringify(options.daemonTarget.home)}` : `--host ${JSON.stringify(describeDaemonTarget(options.daemonTarget))}`}`,
                appliedPaths: payload.appliedPaths,
                restartRequiredPaths: payload.restartRequiredPaths,
                overrideControlledPaths: payload.overrideControlledPaths,
            },
            schema: daemonReloadSchema,
        };
    }
    finally {
        await client.close();
    }
}
export function daemonReloadCommand() {
    return addJsonAndDaemonHostOptions(new Command("reload").description("Reload config.json without restarting")).action(withOutput(runDaemonReloadCommand));
}
//# sourceMappingURL=reload.js.map