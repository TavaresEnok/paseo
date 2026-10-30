import { resolve } from "node:path";
export function createWorkspaceRuntimeStore() {
    const snapshots = new Map();
    return {
        get(cwd) {
            return snapshots.get(resolve(cwd)) ?? null;
        },
        set(snapshot) {
            snapshots.set(resolve(snapshot.cwd), snapshot);
        },
        remove(cwd) {
            snapshots.delete(resolve(cwd));
        },
    };
}
//# sourceMappingURL=index.js.map