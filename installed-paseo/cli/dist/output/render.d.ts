/**
 * Main render dispatcher for CLI output.
 *
 * Selects the appropriate renderer based on output options.
 */
import type { AnyCommandResult, CommandError, OutputOptions } from "./types.js";
/** Default output options */
export declare const defaultOutputOptions: OutputOptions;
/** Render command result to string based on output options */
export declare function render<T>(result: AnyCommandResult<T>, options?: Partial<OutputOptions>): string;
/** Convert an unknown error to a CommandError */
export declare function toCommandError(error: unknown): CommandError;
/** Render an error to string based on output options */
export declare function renderError(error: CommandError, options?: Partial<OutputOptions>): string;
//# sourceMappingURL=render.d.ts.map