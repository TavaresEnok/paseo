import type { DaemonTarget } from "../../utils/daemon-target.js";
import type { CommandError, CommandOptions } from "../../output/index.js";
export interface TerminalCommandOptions extends CommandOptions {
    host?: string;
}
export declare function connectTerminalClient(target: DaemonTarget): Promise<{
    client: import("@getpaseo/client").PaseoApi;
    daemonHost: string;
    close: () => Promise<void>;
}>;
export declare function toTerminalCommandError(code: string, action: string, err: unknown): CommandError;
export declare function resolveTerminalId(client: Awaited<ReturnType<typeof connectTerminalClient>>["client"], idOrName: string): Promise<string | null>;
//# sourceMappingURL=shared.d.ts.map