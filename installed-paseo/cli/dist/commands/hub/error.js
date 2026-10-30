export class HubCommandError extends Error {
    constructor(code, message, details) {
        super(message);
        this.code = code;
        this.details = details;
        this.name = "HubCommandError";
    }
}
//# sourceMappingURL=error.js.map