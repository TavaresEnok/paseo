/**
 * YAML renderer for CLI output.
 *
 * Renders structured data as YAML for machine consumption and human readability.
 */
import YAML from "yaml";
/** Render command result as YAML */
export function renderYaml(result, _options) {
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
                    return YAML.stringify(serialized[0]);
                }
            }
            return YAML.stringify(serialized);
        }
        else {
            const serialized = schema.serialize(result.data);
            return YAML.stringify(serialized);
        }
    }
    return YAML.stringify(result.data);
}
/** Render a single item as YAML document (for streaming) */
export function renderYamlDoc(item, serialize) {
    const output = serialize ? serialize(item) : item;
    return YAML.stringify(output);
}
//# sourceMappingURL=yaml.js.map