import type { Command } from "commander";
import type { SingleResult } from "../../output/index.js";
import { type TerminalCommandOptions } from "./shared.js";
import { type TerminalKillRow } from "./schema.js";
export declare function runKillCommand(terminalId: string, options: TerminalCommandOptions, _command: Command): Promise<SingleResult<TerminalKillRow>>;
//# sourceMappingURL=kill.d.ts.map