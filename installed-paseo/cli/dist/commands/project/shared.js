export const projectSchema = {
    idField: "projectId",
    columns: [
        { header: "PROJECT ID", field: "projectId", width: 20 },
        { header: "NAME", field: "name", width: 24 },
        { header: "KIND", field: "kind", width: 10 },
        { header: "PATH", field: "path", width: 42 },
    ],
};
export function toProjectRow(project) {
    return {
        projectId: project.projectId,
        name: project.projectDisplayName,
        kind: project.projectKind,
        path: project.projectRootPath,
    };
}
//# sourceMappingURL=shared.js.map