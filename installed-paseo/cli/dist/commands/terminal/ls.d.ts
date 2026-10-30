import type { Command } from "commander";
import type { ListResult } from "../../output/index.js";
import { type TerminalCommandOptions } from "./shared.js";
import { type TerminalRow } from "./schema.js";
export interface TerminalLsOptions extends TerminalCommandOptions {
    workspace?: string;
    all?: boolean;
    cwd?: string;
}
export declare function runLsCommand(options: TerminalLsOptions, _command: Command): Promise<ListResult<TerminalRow>>;
//# sourceMappingURL=ls.d.ts.map