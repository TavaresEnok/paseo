import type { Command } from "commander";
import type { CommandOptions, SingleResult } from "../../output/index.js";
import { type ProjectRow } from "./shared.js";
export declare function resolveProjectPath(input: {
    pathArg?: string;
    cwd: string;
    daemonTarget?: string;
}): string;
export declare function runCreateCommand(pathArg: string | undefined, options: CommandOptions, _command: Command): Promise<SingleResult<ProjectRow>>;
//# sourceMappingURL=create.d.ts.map