export class ApiError extends Error {
    apiName;
    statusCode;
    retryable;
    details;
    constructor(params) {
        super(params.message);
        this.name = "ApiError";
        this.apiName = params.apiName;
        this.statusCode = params.statusCode;
        this.retryable = params.retryable;
        this.details = params.details;
    }
}
export class ValidationError extends Error {
    field;
    issues;
    constructor(message, issues) {
        super(message);
        this.name = "ValidationError";
        this.issues = issues;
    }
}
//# sourceMappingURL=errors.js.map