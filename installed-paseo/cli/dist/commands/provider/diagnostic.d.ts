import type { Command } from "commander";
import type { CommandOptions, OutputSchema, SingleResult } from "../../output/index.js";
export interface ProviderDiagnosticResult {
    provider: string;
    diagnostic: string;
}
export declare const providerDiagnosticSchema: OutputSchema<ProviderDiagnosticResult>;
export interface ProviderDiagnosticOptions extends CommandOptions {
    host?: string;
}
export declare function runDiagnosticCommand(provider: string, options: ProviderDiagnosticOptions, _command: Command): Promise<SingleResult<ProviderDiagnosticResult>>;
//# sourceMappingURL=diagnostic.d.ts.map