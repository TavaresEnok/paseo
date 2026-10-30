import { Command } from "commander";
import { type CommandOptions } from "../../output/index.js";
export declare function startCommand(): Command;
export declare function runStart(options: CommandOptions, _command: Command): Promise<{
    type: "single";
    data: {
        action: string;
        home: string;
        pid: number;
        listen: string | null;
        logPath: string;
    };
    schema: {
        idField: "pid";
        columns: never[];
        renderHuman: () => string;
    };
}>;
export declare function daemonRunCommand(): Command;
//# sourceMappingURL=start.d.ts.map