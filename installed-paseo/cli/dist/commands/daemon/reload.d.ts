import { Command } from "commander";
import type { CommandOptions, OutputSchema, SingleResult } from "../../output/index.js";
export interface DaemonReloadResult {
    restartCommand: string;
    appliedPaths: string[];
    restartRequiredPaths: string[];
    overrideControlledPaths: string[];
}
export declare const daemonReloadSchema: OutputSchema<DaemonReloadResult>;
export declare function runDaemonReloadCommand(options: CommandOptions, _command: Command): Promise<SingleResult<DaemonReloadResult>>;
export declare function daemonReloadCommand(): Command;
//# sourceMappingURL=reload.d.ts.map