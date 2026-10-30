/**
 * JSON renderer for CLI output.
 *
 * Renders structured data as formatted JSON for machine consumption.
 */
/** Render command result as JSON */
export function renderJson(result, _options) {
    const { schema } = result;
    // Apply custom serializer if provided
    if (schema.serialize) {
        if (result.type === "list") {
            // If all items serialize to the same object, return just one
            // This handles the case where a list of key-value rows should serialize
            // to a single structured object
            const serialized = result.data.map((item) => schema.serialize(item));
            if (serialized.length > 0) {
                const first = JSON.stringify(serialized[0]);
                const allSame = serialized.every((s) => JSON.stringify(s) === first);
                if (allSame) {
                    return JSON.stringify(serialized[0], null, 2);
                }
            }
            return JSON.stringify(serialized, null, 2);
        }
        else {
            const serialized = schema.serialize(result.data);
            return JSON.stringify(serialized, null, 2);
        }
    }
    return JSON.stringify(result.data, null, 2);
}
/** Render a single item as JSON line (for NDJSON streaming) */
export function renderJsonLine(item, serialize) {
    const output = serialize ? serialize(item) : item;
    return JSON.stringify(output);
}
//# sourceMappingURL=json.js.map