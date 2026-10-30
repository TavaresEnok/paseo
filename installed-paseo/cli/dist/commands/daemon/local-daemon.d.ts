import { Command } from "commander";
export declare function launchLocalDaemon(options: {
    home: string;
    timeoutMs?: number;
    foreground?: boolean;
}): Promise<{
    instance: import("@getpaseo/server/daemon-control").DaemonInstance;
    spawned: boolean;
    exitCode?: number;
}>;
export declare function parseTimeoutMs(raw: unknown, fallback?: number): number;
export declare function rejectRemovedLaunchFlags(command: Command): Command;
//# sourceMappingURL=local-daemon.d.ts.map