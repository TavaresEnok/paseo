/**
 * JSON renderer for CLI output.
 *
 * Renders structured data as formatted JSON for machine consumption.
 */
import type { AnyCommandResult, OutputOptions } from "./types.js";
/** Render command result as JSON */
export declare function renderJson<T>(result: AnyCommandResult<T>, _options: OutputOptions): string;
/** Render a single item as JSON line (for NDJSON streaming) */
export declare function renderJsonLine<T>(item: T, serialize?: (data: T) => unknown): string;
//# sourceMappingURL=json.d.ts.map