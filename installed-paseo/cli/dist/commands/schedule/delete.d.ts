import type { Command } from "commander";
import type { SingleResult } from "../../output/index.js";
import { type ScheduleCommandOptions } from "./shared.js";
interface ScheduleDeleteRow {
    id: string;
    status: string;
}
export declare function runDeleteCommand(id: string, options: ScheduleCommandOptions, _command: Command): Promise<SingleResult<ScheduleDeleteRow>>;
export {};
//# sourceMappingURL=delete.d.ts.map