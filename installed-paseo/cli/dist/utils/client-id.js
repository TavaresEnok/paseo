import { ensurePrivateDirectory } from "@getpaseo/server/daemon-control";
import { readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { join } from "node:path";
function normalizeClientId(value) {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
}
function generateClientId() {
    return `cid_${randomUUID().replace(/-/g, "")}`;
}
export async function getOrCreateCliClientId(home) {
    const clientSessionKeyFile = join(home, "cli-client-id");
    try {
        const existing = normalizeClientId(await readFile(clientSessionKeyFile, "utf8"));
        if (existing) {
            return existing;
        }
    }
    catch (error) {
        const code = error?.code;
        if (code !== "ENOENT") {
            throw error;
        }
    }
    const nextValue = generateClientId();
    ensurePrivateDirectory(home);
    await writeFile(clientSessionKeyFile, nextValue, { mode: 0o600 });
    return nextValue;
}
//# sourceMappingURL=client-id.js.map