/**
 * Quiet renderer for CLI output.
 *
 * Outputs only ID fields, one per line. Useful for scripting and pipelines.
 */
/** Extract ID from item using schema definition */
function getId(item, idField) {
    if (typeof idField === "function") {
        return idField(item);
    }
    return String(item[idField]);
}
/** Render command result in quiet mode (IDs only) */
export function renderQuiet(result, _options) {
    if (result.type === "single") {
        return getId(result.data, result.schema.idField);
    }
    else {
        return result.data.map((item) => getId(item, result.schema.idField)).join("\n");
    }
}
//# sourceMappingURL=quiet.js.map