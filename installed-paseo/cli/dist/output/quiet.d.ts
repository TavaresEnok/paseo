/**
 * Quiet renderer for CLI output.
 *
 * Outputs only ID fields, one per line. Useful for scripting and pipelines.
 */
import type { AnyCommandResult, OutputOptions } from "./types.js";
/** Render command result in quiet mode (IDs only) */
export declare function renderQuiet<T>(result: AnyCommandResult<T>, _options: OutputOptions): string;
//# sourceMappingURL=quiet.d.ts.map