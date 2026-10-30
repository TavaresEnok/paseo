import type { Command } from "commander";
import { type TerminalCommandOptions } from "./shared.js";
export interface TerminalCaptureOptions extends TerminalCommandOptions {
    start?: string;
    end?: string;
    scrollback?: boolean;
    ansi?: boolean;
}
export declare function runCaptureCommand(terminalId: string, options: TerminalCaptureOptions, _command: Command): Promise<void>;
//# sourceMappingURL=capture.d.ts.map