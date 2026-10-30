import { Command } from "commander";
import { connectToDaemon } from "../../utils/client.js";
import { addJsonAndDaemonHostOptions } from "../../utils/command-options.js";
import { withOutput } from "../../output/index.js";
import { usageSchema } from "./presentation.js";
export async function runUsageCommand(options, selection, connect = connectToDaemon) {
    const conflictingSelectors = selection.kind === "inspect" && options.agent !== undefined;
    if (conflictingSelectors) {
        throw {
            code: "INVALID_OPTIONS",
            message: "--agent cannot be combined with usage inspect. Use usage ls --agent <id> for agent account usage, or usage inspect <report-id> for an exact report.",
        };
    }
    const client = await connect({ target: options.daemonTarget });
    try {
        if (client.getLastServerInfoMessage()?.features?.usageSources !== true) {
            throw { code: "UNSUPPORTED_HOST", message: "Update the host to use usage reports." };
        }
        if (selection.kind === "list") {
            const { reports } = await client.listUsageReports({
                agentId: options.agent,
                forceRefresh: options.refresh,
            });
            return { type: "list", data: reports, schema: usageSchema };
        }
        // Report-ID queries only select known accounts. Discover before selecting, including on cold hosts.
        const { reports } = await client.listUsageReports();
        let entry = reports.find((report) => report.id === selection.id);
        if (entry && options.refresh) {
            const refreshed = await client.listUsageReports({
                reportIds: [selection.id],
                forceRefresh: true,
            });
            entry = refreshed.reports.find((report) => report.id === selection.id);
        }
        if (!entry) {
            throw { code: "REPORT_NOT_FOUND", message: `Unknown usage report: ${selection.id}` };
        }
        return { type: "single", data: entry, schema: usageSchema };
    }
    finally {
        await client.close().catch(() => { });
    }
}
function addListOptions(command) {
    return addJsonAndDaemonHostOptions(command)
        .option("--agent <id>", "Show account quota associated with this agent (not agent token consumption)")
        .option("--refresh", "Refresh usage instead of using the host cache");
}
export function createUsageCommand() {
    const usage = addListOptions(new Command("usage").description("Show account usage reports"));
    const list = (options, _command) => runUsageCommand(options, { kind: "list" });
    usage.action(withOutput(list));
    addListOptions(usage.command("ls").description("List account quotas and balances")).action(withOutput(list));
    addJsonAndDaemonHostOptions(usage
        .command("inspect")
        .description("Show a complete account usage report")
        .argument("<report-id>", "Exact opaque Report ID")
        .option("--refresh", "Refresh the selected report instead of using the host cache")).action(withOutput((id, options, _command) => runUsageCommand(options, { kind: "inspect", id })));
    return usage;
}
//# sourceMappingURL=index.js.map