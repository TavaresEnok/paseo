import { existsSync, statSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
export function isPathLikeArg(arg) {
    return (arg === "." ||
        arg === ".." ||
        arg.startsWith("./") ||
        arg.startsWith("../") ||
        arg.startsWith("/") ||
        arg === "~" ||
        arg.startsWith("~/") ||
        /^[A-Za-z]:[\\/]/.test(arg));
}
export function expandUserPath(inputPath) {
    if (inputPath === "~") {
        return homedir();
    }
    if (inputPath.startsWith("~/")) {
        return path.join(homedir(), inputPath.slice(2));
    }
    return inputPath;
}
export function isExistingDirectory(input) {
    const resolvedPath = path.resolve(input.cwd, expandUserPath(input.pathArg));
    if (!existsSync(resolvedPath)) {
        return false;
    }
    return statSync(resolvedPath).isDirectory();
}
export function classifyInvocation(input) {
    const [firstArg] = input.argv;
    if (!firstArg) {
        return { kind: "cli", argv: input.argv };
    }
    if (firstArg.startsWith("-")) {
        return { kind: "cli", argv: input.argv };
    }
    if (input.knownCommands.has(firstArg)) {
        return { kind: "cli", argv: input.argv };
    }
    if (isExistingDirectory({ pathArg: firstArg, cwd: input.cwd })) {
        return {
            kind: "open-project",
            resolvedPath: path.resolve(input.cwd, expandUserPath(firstArg)),
        };
    }
    return { kind: "cli", argv: input.argv };
}
//# sourceMappingURL=classify.js.map