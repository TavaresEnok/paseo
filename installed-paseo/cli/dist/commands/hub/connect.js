import { withOutput } from "../../output/index.js";
import { addJsonAndDaemonHostOptions } from "../../utils/command-options.js";
import { resolveHubCredential, resolveHubOrigin } from "./authority.js";
import { withHubDaemon } from "./daemon-client.js";
import { hubStatusResult } from "./status-output.js";
import { reportHubProgress } from "./reporter.js";
import { addHubResolutionHelp } from "./help.js";
export async function runHubConnect(originInput, options, dependencies) {
    const resolution = {
        options: { origin: originInput, apiKey: options.apiKey },
        env: dependencies.env,
        credentials: dependencies.credentials,
    };
    const origin = resolveHubOrigin(resolution);
    reportHubProgress(dependencies.reporter, options, `Connecting this daemon to ${origin}`);
    const credential = resolveHubCredential({ ...resolution, origin });
    const token = await dependencies.hub.issueEnrollmentToken(origin, credential);
    const permissions = options.permissions ?? options.permission ?? [];
    return withHubDaemon(dependencies.daemon, options.daemonTarget, async (daemon) => {
        const response = await daemon.connectHub(origin, token, permissions);
        if (response.status.hubOrigin !== null &&
            !samePermissions(response.status.permissions, permissions)) {
            await daemon.disconnectHub(false).catch(() => undefined);
            throw new Error("The daemon did not honor the requested Hub access. Update Paseo before connecting it.");
        }
        return hubStatusResult(response.status);
    });
}
export function addHubConnectCommand(parent, dependencies) {
    addJsonAndDaemonHostOptions(addHubResolutionHelp(parent
        .command("connect")
        .description("Enroll this daemon with a Paseo Hub")
        .argument("[origin]", "Paseo Hub origin")
        .option("--api-key <secret>", "Organization API key")
        .option("--permission <permission...>", "Grant daemon permission during connection"))).action(withOutput(async (...args) => {
        const origin = args[0];
        const options = args.at(-2);
        return runHubConnect(origin, options, dependencies);
    }));
}
function samePermissions(actual, expected) {
    return actual.length === expected.length && expected.every((scope) => actual.includes(scope));
}
//# sourceMappingURL=connect.js.map