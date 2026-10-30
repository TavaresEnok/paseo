export class PaseoToolInputError extends Error {
    constructor(message, issues) {
        super(message);
        this.issues = issues;
        this.status = 400;
        this.name = "PaseoToolInputError";
    }
}
//# sourceMappingURL=types.js.map