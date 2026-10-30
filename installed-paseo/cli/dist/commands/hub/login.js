import { withOutput } from "../../output/index.js";
import { addJsonOption } from "../../utils/command-options.js";
import { resolveHubOrigin } from "./authority.js";
import { reportHubProgress } from "./reporter.js";
import { addHubResolutionHelp } from "./help.js";
const schema = {
    idField: "origin",
    columns: [
        { header: "HUB", field: "origin" },
        { header: "STATUS", field: "status" },
    ],
};
export async function runHubLogin(originInput, options, dependencies) {
    const origin = resolveHubOrigin({
        options: { origin: originInput },
        env: dependencies.env,
        credentials: dependencies.credentials,
    });
    reportHubProgress(dependencies.reporter, options, `Logging in to ${origin}`);
    const credential = await dependencies.flow.authorize(origin);
    dependencies.credentials.save({ origin, credential });
    reportHubProgress(dependencies.reporter, options, "Logged in");
    if (!options.json &&
        dependencies.isInteractive?.() &&
        dependencies.continueGuidedSetup !== undefined) {
        await dependencies.continueGuidedSetup(origin, options.daemonTarget);
    }
    return { type: "single", data: { origin, status: "logged_in" }, schema };
}
export function addHubLoginCommand(parent, dependencies) {
    addJsonOption(addHubResolutionHelp(parent
        .command("login")
        .description("Log in to a Paseo Hub for CLI access")
        .argument("[origin]", "Paseo Hub origin"))).action(withOutput(async (...args) => {
        const origin = args[0];
        const options = args.at(-2);
        return runHubLogin(origin, options, dependencies);
    }));
}
//# sourceMappingURL=login.js.map