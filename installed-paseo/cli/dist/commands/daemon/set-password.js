import path from "node:path";
import { isCancel, password as passwordPrompt } from "@clack/prompts";
import { hashDaemonPassword } from "@getpaseo/server/auth";
import { readPersistedConfig, savePersistedConfig, } from "@getpaseo/server/configuration";
import { resolvePaseoHome } from "@getpaseo/server/daemon-control";
const CONFIG_FILENAME = "config.json";
const setPasswordResultSchema = {
    idField: "action",
    columns: [
        { header: "STATUS", field: "action", color: () => "green" },
        { header: "CONFIG", field: "configPath" },
        { header: "RESTART", field: "restartCommand" },
    ],
    renderHuman: (result, options) => {
        const data = result.data;
        const rows = [
            `Password written to ${data.configPath}`,
            "Restart the daemon for the change to take effect.",
            `Run: ${data.restartCommand}`,
        ];
        if (options.format === "table") {
            return rows.join("\n");
        }
        return data.message;
    },
};
function createCommandError(code, message, details) {
    return { code, message, ...(details ? { details } : {}) };
}
function terminalPasswordPrompt() {
    if (!process.stdin.isTTY) {
        throw createCommandError("PASSWORD_TTY_REQUIRED", "paseo daemon set-password needs a terminal to read the password", "Run it in an interactive terminal, or set PASEO_PASSWORD in the daemon's environment instead.");
    }
    return (message) => passwordPrompt({ message });
}
async function promptForPassword(promptPassword) {
    const first = await promptPassword("New daemon password");
    if (isCancel(first)) {
        throw createCommandError("PASSWORD_CANCELLED", "Password update cancelled");
    }
    if (typeof first !== "string" || first.length === 0) {
        throw createCommandError("PASSWORD_REQUIRED", "Password cannot be empty");
    }
    const second = await promptPassword("Confirm daemon password");
    if (isCancel(second)) {
        throw createCommandError("PASSWORD_CANCELLED", "Password update cancelled");
    }
    if (first !== second) {
        throw createCommandError("PASSWORD_MISMATCH", "Passwords do not match");
    }
    return first;
}
export async function setDaemonPasswordInConfig(newPassword, options = {}) {
    const paseoHome = resolvePaseoHome({ PASEO_HOME: options.home });
    const configPath = path.join(paseoHome, CONFIG_FILENAME);
    const persisted = readPersistedConfig(paseoHome);
    const nextConfig = {
        ...persisted,
        daemon: {
            ...persisted.daemon,
            auth: {
                ...persisted.daemon?.auth,
                password: hashDaemonPassword(newPassword),
            },
        },
    };
    savePersistedConfig(paseoHome, nextConfig);
    return {
        action: "password_set",
        configPath,
        restartCommand: `paseo daemon restart --home ${JSON.stringify(paseoHome)}`,
        message: `Password written to ${configPath}\nRestart the daemon for the change to take effect.\nRun: paseo daemon restart --home ${JSON.stringify(paseoHome)}`,
    };
}
export async function runSetPasswordCommand(options, _command) {
    const promptPassword = typeof options.promptPassword === "function"
        ? options.promptPassword
        : terminalPasswordPrompt();
    const newPassword = await promptForPassword(promptPassword);
    const result = await setDaemonPasswordInConfig(newPassword, {
        home: options.daemonTarget.kind === "instance" ? options.daemonTarget.home : undefined,
    });
    return {
        type: "single",
        data: result,
        schema: setPasswordResultSchema,
    };
}
//# sourceMappingURL=set-password.js.map