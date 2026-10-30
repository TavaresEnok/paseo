/**
 * Command wrapper for automatic output rendering.
 *
 * Wraps command handlers to automatically render results and handle errors.
 */
import type { Command } from "commander";
import type { AnyCommandResult, OutputOptions } from "./types.js";
/** Options that include output settings from global options */
export interface CommandOptions extends Partial<OutputOptions> {
    daemonTarget: import("../utils/daemon-target.js").DaemonTarget;
    home?: string;
    /** Daemon host target from --host option */
    host?: string;
    /** JSON output flag from --json option */
    json?: boolean;
    [key: string]: unknown;
}
/**
 * Wrap a command handler to automatically render output.
 *
 * The wrapped handler should return a CommandResult. The wrapper will:
 * 1. Call the handler
 * 2. Render the result using the appropriate format
 * 3. Write to stdout
 * 4. Handle errors by rendering to stderr and exiting with code 1
 *
 * @example
 * ```typescript
 * program
 *   .command('list')
 *   .action(withOutput(async (options) => {
 *     const data = await fetchData()
 *     return { type: 'list', data, schema }
 *   }))
 * ```
 */
export declare function withOutput<T, Args extends unknown[]>(handler: (...args: [...Args, CommandOptions, Command]) => Promise<AnyCommandResult<T>>): (...args: [...Args, CommandOptions, Command]) => Promise<void>;
/**
 * Helper to create output options from partial input.
 * Useful for testing or manual rendering.
 */
export declare function createOutputOptions(partial?: Partial<OutputOptions>): OutputOptions;
//# sourceMappingURL=with-output.d.ts.map