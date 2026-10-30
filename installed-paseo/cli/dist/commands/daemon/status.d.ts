import { Command } from "commander";
import { type CommandOptions } from "../../output/index.js";
export declare function daemonStatusCommand(): Command;
export declare function runStatusCommand(options: CommandOptions, _command: Command): Promise<{
    type: "single";
    data: Record<string, unknown>;
    schema: {
        idField: () => string;
        columns: never[];
        renderHuman: () => string;
    };
}>;
//# sourceMappingURL=status.d.ts.map