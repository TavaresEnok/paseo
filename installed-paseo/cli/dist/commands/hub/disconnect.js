import { withOutput } from "../../output/index.js";
import { addJsonAndDaemonHostOptions } from "../../utils/command-options.js";
import { withHubDaemon } from "./daemon-client.js";
import { reportHubProgress } from "./reporter.js";
import { hubStatusResult } from "./status-output.js";
export function runHubDisconnect(options, dependencies) {
    return withHubDaemon(dependencies.daemon, options.daemonTarget, async (client) => {
        const current = (await client.getHubStatus()).status;
        if (current.hubOrigin !== null) {
            reportHubProgress(dependencies.reporter, options, `Disconnecting this daemon from ${current.hubOrigin}`);
        }
        const response = await client.disconnectHub(options.force ?? false);
        return hubStatusResult(response.status, response.warning);
    });
}
export function addHubDisconnectCommand(parent, dependencies) {
    addJsonAndDaemonHostOptions(parent
        .command("disconnect")
        .option("--force", "Remove local authority without notifying the Hub")).action(withOutput(async (...args) => {
        const options = args.at(-2);
        return runHubDisconnect(options, dependencies);
    }));
}
//# sourceMappingURL=disconnect.js.map