import { Command } from "commander";
import { type CommandOptions } from "../../output/index.js";
export declare function daemonRestartCommand(): Command;
export declare function runRestartCommand(options: CommandOptions, _command: Command): Promise<{
    type: "single";
    data: {
        action: string;
        target: string;
        supervisorPid: number | null;
        previousWorkerPid: number;
        workerPid: number;
        acknowledged: boolean;
    };
    schema: {
        idField: "action";
        columns: never[];
        renderHuman: () => string;
    };
}>;
//# sourceMappingURL=restart.d.ts.map