import path from "node:path";
const DEFAULT_DAEMON_LOG_FILENAME = "daemon.log";
const DEFAULT_LOG_ROTATE_SIZE = "10m";
const DEFAULT_LOG_ROTATE_MAX_FILES = 3;
export function resolveSupervisorLogFile(paseoHome, persistedConfig, env = process.env) {
    const configuredFile = persistedConfig.log?.file;
    const configuredPath = configuredFile?.path;
    const envRotateSize = env.PASEO_LOG_ROTATE_SIZE?.trim();
    const envRotateMaxFiles = parseOptionalPositiveInteger(env.PASEO_LOG_ROTATE_COUNT);
    let logPath = path.join(paseoHome, DEFAULT_DAEMON_LOG_FILENAME);
    if (configuredPath) {
        logPath = path.isAbsolute(configuredPath)
            ? configuredPath
            : path.resolve(paseoHome, configuredPath);
    }
    return {
        path: logPath,
        rotate: {
            maxSize: configuredFile?.rotate?.maxSize ?? envRotateSize ?? DEFAULT_LOG_ROTATE_SIZE,
            maxFiles: configuredFile?.rotate?.maxFiles ?? envRotateMaxFiles ?? DEFAULT_LOG_ROTATE_MAX_FILES,
        },
    };
}
function parseOptionalPositiveInteger(value) {
    if (value === undefined) {
        return undefined;
    }
    const parsed = Number.parseInt(value.trim(), 10);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}
//# sourceMappingURL=supervisor-log-config.js.map