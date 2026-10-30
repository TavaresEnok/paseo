const schema = {
    idField: "state",
    columns: [
        { header: "STATE", field: "state" },
        { header: "HUB", field: "hub" },
        { header: "DAEMON", field: "daemonId" },
        { header: "PERMISSIONS", field: "permissions" },
        { header: "CONNECTED", field: "connectedAt" },
        { header: "ERROR", field: "error" },
        { header: "WARNING", field: "warning" },
    ],
};
export function hubStatusResult(status, warning, reportedHubOrigin = status.hubOrigin) {
    return {
        type: "list",
        data: [
            {
                state: status.state,
                daemonId: status.daemonId,
                hub: reportedHubOrigin,
                permissions: status.permissions.join(", "),
                connectedAt: status.connectedAt,
                error: status.lastError,
                warning,
            },
        ],
        schema,
    };
}
//# sourceMappingURL=status-output.js.map