import { chmodSync, mkdirSync, realpathSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import path from "node:path";
export const PRIVATE_DIRECTORY_MODE = 0o700;
export const PRIVATE_FILE_MODE = 0o600;
function applyPrivateMode(target, mode) {
    if (process.platform === "win32")
        return;
    try {
        chmodSync(target, mode);
    }
    catch {
        // Permissions are not portable; creation must still work on such filesystems.
    }
}
export function ensurePrivateDirectory(directoryPath) {
    mkdirSync(directoryPath, { recursive: true, mode: PRIVATE_DIRECTORY_MODE });
    applyPrivateMode(directoryPath, PRIVATE_DIRECTORY_MODE);
}
export function ensurePrivateFile(filePath) {
    applyPrivateMode(filePath, PRIVATE_FILE_MODE);
}
export function writePrivateFileAtomicSync(filePath, data) {
    ensurePrivateDirectory(path.dirname(filePath));
    const destination = resolveSymlinkedFile(filePath);
    const temporary = path.join(path.dirname(destination), `.${path.basename(destination)}.${process.pid}.${randomUUID()}`);
    try {
        writeFileSync(temporary, data, { mode: PRIVATE_FILE_MODE });
        renameSync(temporary, destination);
        ensurePrivateFile(destination);
    }
    catch (error) {
        rmSync(temporary, { force: true });
        throw error;
    }
}
// Renaming onto a symlink replaces the link, so write to the file it points at.
function resolveSymlinkedFile(filePath) {
    try {
        return realpathSync(filePath);
    }
    catch (error) {
        if (error.code === "ENOENT")
            return filePath;
        throw error;
    }
}
//# sourceMappingURL=private-files.js.map