import type { PaseoTerminal } from "@getpaseo/client";
import type { OutputSchema } from "../../output/index.js";
export type TerminalRow = PaseoTerminal;
export interface TerminalKillRow {
    terminalId: string;
    success: boolean;
}
export declare const terminalSchema: OutputSchema<TerminalRow>;
export declare const terminalKillSchema: OutputSchema<TerminalKillRow>;
//# sourceMappingURL=schema.d.ts.map