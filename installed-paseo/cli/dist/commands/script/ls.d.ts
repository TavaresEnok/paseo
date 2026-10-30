import type { Command } from "commander";
import type { ListResult } from "../../output/index.js";
import { type WorkspaceScriptCommandOptions } from "./shared.js";
import { type WorkspaceScriptRow } from "./schema.js";
export declare function runLsCommand(options: WorkspaceScriptCommandOptions, _command: Command): Promise<ListResult<WorkspaceScriptRow>>;
//# sourceMappingURL=ls.d.ts.map