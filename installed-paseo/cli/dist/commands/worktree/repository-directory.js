import { resolve } from "node:path";
export function resolveRepositoryDirectory(options) {
    const cwd = options.cwd ?? process.cwd();
    if (options.daemonTarget.kind === "instance") {
        return resolve(cwd);
    }
    return cwd;
}
//# sourceMappingURL=repository-directory.js.map