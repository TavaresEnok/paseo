import { Command } from "commander";
import type { DaemonClient } from "@getpaseo/client/internal/daemon-client";
import type { UsageReportEntry } from "@getpaseo/protocol/messages";
import { type ConnectOptions } from "../../utils/client.js";
import { type CommandOptions, type CommandResult } from "../../output/index.js";
interface UsageOptions extends CommandOptions {
    agent?: string;
    refresh?: boolean;
}
type UsageSelection = {
    kind: "list";
} | {
    kind: "inspect";
    id: string;
};
interface UsageClient {
    getLastServerInfoMessage(): {
        features?: {
            usageSources?: boolean;
        };
    } | null;
    listUsageReports: DaemonClient["listUsageReports"];
    close: DaemonClient["close"];
}
type ConnectUsage = (options: ConnectOptions) => Promise<UsageClient>;
export declare function runUsageCommand(options: UsageOptions, selection: UsageSelection, connect?: ConnectUsage): Promise<CommandResult<UsageReportEntry>>;
export declare function createUsageCommand(): Command;
export {};
//# sourceMappingURL=index.d.ts.map