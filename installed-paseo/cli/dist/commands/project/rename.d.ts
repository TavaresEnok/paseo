import type { Command } from "commander";
import type { CommandOptions, SingleResult } from "../../output/index.js";
interface ProjectRenameResult {
    projectId: string;
    name: string | null;
}
export declare function resolveProjectName(input: {
    name?: string;
    reset?: boolean;
}): string | null;
export declare function runRenameCommand(projectId: string, nameArg: string | undefined, options: CommandOptions & {
    reset?: boolean;
}, _command: Command): Promise<SingleResult<ProjectRenameResult>>;
export {};
//# sourceMappingURL=rename.d.ts.map