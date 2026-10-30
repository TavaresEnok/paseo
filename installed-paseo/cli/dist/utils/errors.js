/**
 * Convert unknown thrown values into a user-safe error string.
 */
export function getErrorMessage(error) {
    if (error instanceof Error) {
        return error.message;
    }
    return String(error);
}
//# sourceMappingURL=errors.js.map