import type { Command } from "commander";
import type { CommandOptions, SingleResult } from "../../output/index.js";
interface ProjectDeleteResult {
    projectId: string;
    removedWorkspaceIds: string[];
}
export declare function runDeleteCommand(projectId: string, options: CommandOptions, _command: Command): Promise<SingleResult<ProjectDeleteResult>>;
export {};
//# sourceMappingURL=delete.d.ts.map