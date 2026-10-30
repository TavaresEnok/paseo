import { renderTable } from "../../output/index.js";
function value(input) {
    return input == null ? "-" : String(input);
}
function percent(input) {
    return input == null ? "-" : `${input}%`;
}
function problemText(problem) {
    if (problem.kind === "no_quota")
        return problem.detail;
    const remedy = problem.refreshedBy
        ? `Run ${problem.refreshedBy} to refresh login.`
        : "Sign in again.";
    if (problem.kind === "expired")
        return `Login expired at ${problem.expiresAt}. ${remedy}`;
    return `Login rejected (HTTP ${problem.status}). ${remedy}`;
}
function failureText(report) {
    if (report.status === "error")
        return report.error;
    if (report.status === "unavailable")
        return problemText(report.problem);
    return "-";
}
function windowText(window) {
    return `${window.label}: ${percent(window.usedPct)} used, ${percent(window.remainingPct)} remaining`;
}
function balanceText(balance) {
    return `${balance.label}: ${value(balance.used)} used, ${value(balance.remaining)} remaining, ${value(balance.limit)} limit (${balance.unit})`;
}
function summary(entry) {
    const { report } = entry;
    if (report.status !== "available") {
        const lines = [failureText(report)];
        for (const login of entry.loginErrors ?? [])
            lines.push(`${login.harness}: ${failureText(login.report)}`);
        if (entry.lastSuccessful) {
            lines.push(`Last successful: ${entry.lastSuccessful.fetchedAt}`);
            lines.push(...availableSummary(entry.lastSuccessful.report).map((line) => `Retained: ${line}`));
        }
        else
            lines.push("No successful update");
        return lines;
    }
    return [...availableSummary(report), `Last successful: ${successfulTime(entry)}`];
}
function availableSummary(report) {
    const lines = report.windows.map(windowText);
    lines.push(...(report.balances ?? []).map(balanceText));
    return lines.length ? lines : ["-"];
}
const summarySchema = {
    idField: "id",
    columns: [
        { header: "REPORT ID", field: "id" },
        { header: "SOURCE", field: "source" },
        { header: "ACCOUNT", field: "account" },
        { header: "STATUS", field: "status" },
        { header: "USAGE", field: "usage" },
        { header: "FETCHED (LATEST ATTEMPT)", field: "fetched" },
    ],
};
function inspect(entry) {
    const lines = [
        `Report ID: ${entry.id}`,
        `Source: ${entry.sourceLabel}`,
        `Source ID: ${entry.sourceId}`,
        `Account: ${value(entry.account.label)}`,
        `Status: ${entry.report.status}`,
        `Latest attempt: ${value(entry.fetchedAt)}`,
    ];
    const report = entry.report.status === "available" ? entry.report : entry.lastSuccessful?.report;
    const successfulAt = successfulTime(entry);
    lines.push(successfulAt ? `Last successful: ${successfulAt}` : "No successful update");
    if (entry.report.status !== "available")
        lines.push(`Reason: ${failureText(entry.report)}`);
    if (report) {
        if (entry.report.status !== "available")
            lines.push("Retained usage:");
        lines.push(...availableDetails(report));
    }
    if (entry.loginErrors?.length) {
        lines.push("Login failures:");
        for (const login of entry.loginErrors)
            lines.push(`  ${login.harness}: ${failureText(login.report)}`);
    }
    return lines.join("\n");
}
export const usageSchema = {
    idField: "id",
    columns: [],
    renderHuman(result, options) {
        if (result.type === "single")
            return inspect(result.data);
        if (!result.data.length)
            return "No usage reports returned";
        const rows = [];
        for (const entry of result.data) {
            for (const [index, usage] of summary(entry).entries()) {
                const first = index === 0;
                rows.push({
                    id: first ? entry.id : "",
                    source: first ? entry.sourceLabel : "",
                    account: first ? value(entry.account.label) : "",
                    status: first ? entry.report.status : "",
                    usage,
                    fetched: first ? value(entry.fetchedAt) : "",
                });
            }
        }
        return renderTable({ type: "list", data: rows, schema: summarySchema }, options);
    },
};
function availableDetails(report) {
    const lines = [];
    lines.push(`Plan: ${value(report.planLabel)}`, "Windows:");
    if (!report.windows.length)
        lines.push("  -");
    for (const window of report.windows) {
        lines.push(`  ${windowText(window)} [${window.id}]`, `    Resets: ${value(window.resetsAt)}`);
        if (window.runsOutAt != null)
            lines.push(`    Runs out: ${window.runsOutAt}`);
        if (window.shortfallPct != null)
            lines.push(`    Shortfall: ${percent(window.shortfallPct)}`);
    }
    lines.push("Balances:");
    if (!report.balances?.length)
        lines.push("  -");
    for (const balance of report.balances ?? []) {
        lines.push(`  ${balanceText(balance)} [${balance.id}]`, `    Resets: ${value(balance.resetsAt)}`);
    }
    lines.push("Details:");
    if (!report.details?.length)
        lines.push("  -");
    for (const detail of report.details ?? [])
        lines.push(`  ${detail.label}: ${detail.value}`);
    return lines;
}
function successfulTime(entry) {
    // COMPAT(usageSuccessfulAt): added in v0.12.0, remove after 2027-04-17 once daemon floor >= v0.12.0.
    // Only available reports from older daemons can use their attempt timestamp as freshness.
    if (entry.report.status === "available")
        return entry.successfulAt ?? entry.fetchedAt;
    return entry.lastSuccessful?.fetchedAt;
}
//# sourceMappingURL=presentation.js.map