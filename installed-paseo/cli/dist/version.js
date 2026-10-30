import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
export function resolveCliVersion() {
    const packageJson = require("../package.json");
    if (typeof packageJson.version === "string" && packageJson.version.trim().length > 0) {
        return packageJson.version.trim();
    }
    throw new Error("Unable to resolve @getpaseo/cli version from package.json.");
}
//# sourceMappingURL=version.js.map