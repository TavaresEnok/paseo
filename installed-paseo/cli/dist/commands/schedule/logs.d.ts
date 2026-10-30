import type { Command } from "commander";
import type { ListResult } from "../../output/index.js";
import { type ScheduleLogRow } from "./schema.js";
import { type ScheduleCommandOptions } from "./shared.js";
export declare function runLogsCommand(id: string, options: ScheduleCommandOptions, _command: Command): Promise<ListResult<ScheduleLogRow>>;
//# sourceMappingURL=logs.d.ts.map