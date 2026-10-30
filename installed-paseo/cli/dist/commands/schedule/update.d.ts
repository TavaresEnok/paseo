import type { Command } from "commander";
import type { ListResult } from "../../output/index.js";
import { type ScheduleInspectRow } from "./schema.js";
import { type ScheduleCommandOptions } from "./shared.js";
export interface ScheduleUpdateOptions extends ScheduleCommandOptions {
    every?: string;
    cron?: string;
    timezone?: string;
    name?: string;
    prompt?: string;
    provider?: string;
    model?: string;
    mode?: string;
    cwd?: string;
    maxRuns?: string | false;
    expiresIn?: string | false;
}
export declare function runUpdateCommand(id: string, options: ScheduleUpdateOptions, _command: Command): Promise<ListResult<ScheduleInspectRow>>;
//# sourceMappingURL=update.d.ts.map