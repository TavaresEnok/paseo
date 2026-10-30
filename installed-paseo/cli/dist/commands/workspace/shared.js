export const workspaceSchema = {
    idField: "workspaceId",
    columns: [
        { header: "WORKSPACE ID", field: "workspaceId", width: 20 },
        { header: "PROJECT", field: "project", width: 20 },
        { header: "NAME", field: "name", width: 22 },
        { header: "ISOLATION", field: "isolation", width: 10 },
        { header: "CWD", field: "cwd", width: 42 },
    ],
};
/** `--background` listings add a column so hidden workspaces stand out. */
export const workspaceWithBackgroundSchema = {
    ...workspaceSchema,
    columns: [
        ...workspaceSchema.columns,
        { header: "BACKGROUND", field: (row) => (row.background ? "yes" : ""), width: 8 },
    ],
};
export function toWorkspaceRow(workspace) {
    return {
        workspaceId: workspace.id,
        project: workspace.projectDisplayName,
        name: workspace.name,
        isolation: workspace.workspaceKind === "worktree" ? "worktree" : "local",
        cwd: workspace.workspaceDirectory,
        background: workspace.background === true,
    };
}
//# sourceMappingURL=shared.js.map