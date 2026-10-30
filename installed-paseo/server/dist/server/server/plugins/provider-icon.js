import { readFile, realpath, stat } from "node:fs/promises";
import path from "node:path";
import { findSvgIconProblem } from "@getpaseo/plugin";
export async function readPluginProviderIcon(pluginDirectory, iconPath) {
    const resolvedDirectory = await realpath(path.resolve(pluginDirectory));
    const requestedIcon = path.resolve(resolvedDirectory, iconPath);
    assertInsidePluginDirectory(resolvedDirectory, requestedIcon, iconPath);
    const resolvedIcon = await realpath(requestedIcon).catch(() => null);
    if (!resolvedIcon) {
        throw iconError(iconPath, "file does not exist or is not a regular file");
    }
    assertInsidePluginDirectory(resolvedDirectory, resolvedIcon, iconPath);
    const iconStat = await stat(resolvedIcon);
    if (!iconStat.isFile()) {
        throw iconError(iconPath, "file does not exist or is not a regular file");
    }
    const svg = await readFile(resolvedIcon, "utf8");
    const problem = findSvgIconProblem(svg);
    if (problem)
        throw iconError(iconPath, problem);
    return svg;
}
function assertInsidePluginDirectory(resolvedDirectory, resolvedIcon, iconPath) {
    const relative = path.relative(resolvedDirectory, resolvedIcon);
    const escapesDirectory = relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative);
    if (escapesDirectory)
        throw iconError(iconPath, "path leaves the plugin directory");
}
function iconError(iconPath, reason) {
    return new Error(`Invalid plugin provider icon "${iconPath}": ${reason}`);
}
//# sourceMappingURL=provider-icon.js.map