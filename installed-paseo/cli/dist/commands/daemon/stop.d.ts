import { Command } from "commander";
import { type CommandOptions } from "../../output/index.js";
export declare function daemonStopCommand(): Command;
export declare function runStopCommand(options: CommandOptions, _command: Command): Promise<{
    type: "single";
    data: {
        action: string;
        home?: string;
        host?: string;
        pid?: number | null;
        forced?: boolean;
        usedLifecycleRpc?: boolean;
    };
    schema: {
        idField: "action";
        columns: never[];
        renderHuman: () => string;
    };
}>;
//# sourceMappingURL=stop.d.ts.map