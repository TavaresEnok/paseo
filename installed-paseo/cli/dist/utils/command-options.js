import { selectDaemonTarget } from "./daemon-target.js";
const JSON_OPTION_DESCRIPTION = "Output in JSON format";
const DAEMON_HOST_OPTION_DESCRIPTION = "Explicit daemon endpoint: host:port, TCP, socket, SSH, or pairing URL (default: local home)";
const localCommands = new WeakSet();
export function addLocalDaemonOptions(command) {
    localCommands.add(command);
    command.option("--home <path>", "Local daemon home (default: ~/.paseo)");
    return command;
}
export function collectMultiple(value, previous) {
    return previous.concat([value]);
}
export function addJsonOption(command) {
    command.option("--json", JSON_OPTION_DESCRIPTION);
    return command;
}
export function addDaemonHostOption(command) {
    command.option("--host <host>", DAEMON_HOST_OPTION_DESCRIPTION);
    if (!command.options.some((option) => option.long === "--home"))
        command.option("--home <path>", "Select a local daemon home (default: ~/.paseo)");
    return command;
}
export function addJsonAndDaemonHostOptions(command) {
    return addDaemonHostOption(addJsonOption(command));
}
export function withGlobalOptions(handler) {
    return (...args) => {
        const command = args.at(-1);
        const mergedArgs = [...args];
        const options = command.optsWithGlobals();
        const selectors = { home: new Set(), host: new Set() };
        for (let current = command; current; current = current.parent) {
            for (const key of ["home", "host"]) {
                const value = current.opts()[key];
                if (typeof value === "string")
                    selectors[key].add(value);
            }
        }
        for (const key of ["home", "host"]) {
            if (selectors[key].size > 1)
                throw { code: "TARGET_AMBIGUOUS", message: `Conflicting duplicate --${key} selectors.` };
        }
        const localOnly = localCommands.has(command);
        options.daemonTarget = selectDaemonTarget(options, process.env, localOnly);
        mergedArgs[mergedArgs.length - 2] = options;
        return handler(...mergedArgs);
    };
}
//# sourceMappingURL=command-options.js.map