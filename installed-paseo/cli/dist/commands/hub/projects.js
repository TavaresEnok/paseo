import { render, withOutput } from "../../output/index.js";
import { addJsonOption } from "../../utils/command-options.js";
import { resolveHubCredential, resolveHubOrigin } from "./authority.js";
import { reportHubProgress } from "./reporter.js";
import { addHubResolutionHelp } from "./help.js";
const projectSchema = {
    idField: "id",
    columns: [
        { header: "SLUG", field: "slug" },
        { header: "NAME", field: "name" },
        { header: "ID", field: "id" },
        { header: "HUB", field: "origin" },
    ],
};
const schema = {
    idField: "origin",
    columns: [
        { header: "HUB", field: "origin" },
        { header: "PROJECTS", field: (result) => result.projects.length },
    ],
    renderHuman(result, options) {
        const results = result.type === "single" ? [result.data] : result.data;
        const data = results.flatMap((entry) => entry.projects.map((project) => ({ ...project, origin: entry.origin })));
        return render({ type: "list", data, schema: projectSchema }, options);
    },
};
export async function runHubProjects(options, dependencies) {
    const resolution = {
        options: { origin: options.hub, apiKey: options.apiKey },
        env: dependencies.env,
        credentials: dependencies.credentials,
    };
    const origin = resolveHubOrigin(resolution);
    reportHubProgress(dependencies.reporter, options, `Listing projects from ${origin}`);
    const credential = resolveHubCredential({ ...resolution, origin });
    const projects = await dependencies.hub.listProjects(origin, credential);
    return { type: "single", data: { origin, projects }, schema };
}
export function addHubProjectsCommand(parent, dependencies) {
    addJsonOption(addHubResolutionHelp(parent
        .command("projects")
        .description("List projects for the authenticated Hub organization")
        .option("--hub <origin>", "Paseo Hub origin")
        .option("--api-key <secret>", "Organization API key"))).action(withOutput(async (...args) => {
        const options = args.at(-2);
        return runHubProjects(options, dependencies);
    }));
}
//# sourceMappingURL=projects.js.map