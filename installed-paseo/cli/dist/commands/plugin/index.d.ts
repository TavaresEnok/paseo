import { type UpdateOutcome } from "./update.js";
import { Command } from "commander";
import type { PluginListItem, PluginLogEntry } from "@getpaseo/protocol/messages";
import type { CommandOptions, ListResult, SingleResult } from "../../output/index.js";
import { type PluginScaffold } from "./scaffold.js";
interface PluginOptions extends CommandOptions {
    host?: string;
    id?: string;
    ref?: string;
    path?: string;
    all?: boolean;
    version?: string;
    check?: boolean;
    yes?: boolean;
}
export declare function runPluginInitCommand(directory: string, options: PluginOptions, _command: Command): Promise<SingleResult<PluginScaffold>>;
export declare function runPluginListCommand(pluginId: string | undefined, options: PluginOptions, _command: Command): Promise<ListResult<PluginListItem>>;
export declare function runPluginLogsCommand(pluginId: string, options: PluginOptions, _command: Command): Promise<ListResult<PluginLogEntry>>;
export declare function runPluginInstallCommand(source: string, options: PluginOptions, _command: Command): Promise<SingleResult<PluginListItem>>;
export declare function runPluginUpdateCommand(pluginId: string | undefined, options: PluginOptions, _command: Command): Promise<ListResult<UpdateOutcome>>;
export declare function createPluginCommand(): Command;
export {};
//# sourceMappingURL=index.d.ts.map