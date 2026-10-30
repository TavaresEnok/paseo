import type { Command } from "commander";
import type { SingleResult } from "../../output/index.js";
import { type TerminalCommandOptions } from "./shared.js";
import { type TerminalRow } from "./schema.js";
export interface TerminalCreateOptions extends TerminalCommandOptions {
    workspace?: string;
    cwd?: string;
    name?: string;
}
export declare function runCreateCommand(options: TerminalCreateOptions, _command: Command): Promise<SingleResult<TerminalRow>>;
//# sourceMappingURL=create.d.ts.map