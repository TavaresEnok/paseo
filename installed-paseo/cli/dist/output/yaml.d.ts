/**
 * YAML renderer for CLI output.
 *
 * Renders structured data as YAML for machine consumption and human readability.
 */
import type { AnyCommandResult, OutputOptions } from "./types.js";
/** Render command result as YAML */
export declare function renderYaml<T>(result: AnyCommandResult<T>, _options: OutputOptions): string;
/** Render a single item as YAML document (for streaming) */
export declare function renderYamlDoc<T>(item: T, serialize?: (data: T) => unknown): string;
//# sourceMappingURL=yaml.d.ts.map