/**
 * Table renderer for CLI output.
 *
 * Renders structured data as aligned ASCII tables with optional color support.
 */
import type { AnyCommandResult, OutputOptions, OutputSchema } from "./types.js";
/** Render a list result as a table */
export declare function renderTable<T>(result: AnyCommandResult<T>, options: OutputOptions): string;
/** Render just a table header (for streaming) */
export declare function renderTableHeader<T>(schema: OutputSchema<T>, options: OutputOptions, widths?: number[]): string;
/** Render just a table row (for streaming) */
export declare function renderTableRow<T>(item: T, schema: OutputSchema<T>, options: OutputOptions, widths?: number[]): string;
//# sourceMappingURL=table.d.ts.map