import type { Command } from "commander";
import type { ListResult } from "../../output/index.js";
import { type ScheduleInspectRow } from "./schema.js";
import { type ScheduleCommandOptions } from "./shared.js";
export declare function runInspectCommand(id: string, options: ScheduleCommandOptions, _command: Command): Promise<ListResult<ScheduleInspectRow>>;
//# sourceMappingURL=inspect.d.ts.map