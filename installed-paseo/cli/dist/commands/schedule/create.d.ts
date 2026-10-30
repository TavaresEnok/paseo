import type { Command } from "commander";
import type { SingleResult } from "../../output/index.js";
import { type ScheduleCommandOptions, type ScheduleRow } from "./shared.js";
export interface ScheduleCreateOptions extends ScheduleCommandOptions {
    every?: string;
    cron?: string;
    timezone?: string;
    name?: string;
    target?: string;
    provider?: string;
    mode?: string;
    thinking?: string;
    cwd?: string;
    maxRuns?: string;
    expiresIn?: string;
    runNow?: boolean;
}
export declare function runCreateCommand(prompt: string, options: ScheduleCreateOptions, command: Command): Promise<SingleResult<ScheduleRow>>;
//# sourceMappingURL=create.d.ts.map