/**
 * Command wrapper for automatic output rendering.
 *
 * Wraps command handlers to automatically render results and handle errors.
 */
import { render, renderError, toCommandError, defaultOutputOptions } from "./render.js";
import { withGlobalOptions } from "../utils/command-options.js";
function normalizeFormat(raw) {
    const value = typeof raw === "string" ? raw.trim().toLowerCase() : "";
    // Common user expectation: "cli" means "table/human"
    if (value === "cli")
        return "table";
    if (value === "table" || value === "json" || value === "yaml")
        return value;
    const error = {
        code: "INVALID_FORMAT",
        message: `Unsupported output format: ${String(raw)}`,
        details: "Supported formats: table, json, yaml",
    };
    throw error;
}
/** Extract output options from command options */
function extractOutputOptions(options) {
    const hasStructuredOutputSchema = typeof options.outputSchema === "string" && options.outputSchema.trim().length > 0;
    if (hasStructuredOutputSchema) {
        return {
            format: "json",
            quiet: false,
            noHeaders: options.headers === false,
            noColor: options.color === false,
        };
    }
    return {
        format: options.json ? "json" : normalizeFormat(options.format ?? defaultOutputOptions.format),
        quiet: options.quiet ?? defaultOutputOptions.quiet,
        noHeaders: options.headers === false, // Commander uses --no-headers -> headers: false
        noColor: options.color === false, // Commander uses --no-color -> color: false
    };
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
export function withOutput(handler) {
    return withGlobalOptions(async (...args) => {
        const options = args[args.length - 2];
        const outputOptions = extractOutputOptions(options);
        try {
            const result = await handler(...args);
            const output = render(result, outputOptions);
            if (output) {
                process.stdout.write(output + "\n");
            }
        }
        catch (error) {
            const commandError = toCommandError(error);
            const errorOutput = renderError(commandError, outputOptions);
            process.stderr.write(errorOutput + "\n");
            process.exit(1);
        }
    });
}
/**
 * Helper to create output options from partial input.
 * Useful for testing or manual rendering.
 */
export function createOutputOptions(partial = {}) {
    return { ...defaultOutputOptions, ...partial };
}
//# sourceMappingURL=with-output.js.map