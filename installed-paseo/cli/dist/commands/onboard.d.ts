import { Command } from "commander";
import type { CommandOptions } from "../output/index.js";
interface OnboardOptions extends CommandOptions {
    port?: string;
    listen?: string;
    relay?: boolean;
    mcp?: boolean;
    hostnames?: string;
    timeout?: string;
    voice?: "ask" | "enable" | "disable";
}
export declare function onboardCommand(): Command;
export declare function runOnboard(options: OnboardOptions): Promise<void>;
export {};
//# sourceMappingURL=onboard.d.ts.map