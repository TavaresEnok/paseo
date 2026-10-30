import type { Command } from "commander";
import type { SingleResult } from "../../output/index.js";
import { type WorkspaceScriptCommandOptions } from "./shared.js";
import { type WorkspaceScriptRow } from "./schema.js";
export declare function runStopCommand(scriptName: string, options: WorkspaceScriptCommandOptions, _command: Command): Promise<SingleResult<WorkspaceScriptRow>>;
//# sourceMappingURL=stop.d.ts.map