import type { ZodIssue } from "zod";
export declare class ApiError extends Error {
    readonly apiName: string;
    readonly statusCode: number;
    readonly retryable: boolean;
    readonly details?: unknown;
    constructor(params: {
        apiName: string;
        statusCode: number;
        message: string;
        retryable: boolean;
        details?: unknown;
    });
}
export declare class ValidationError extends Error {
    readonly field?: string;
    readonly issues: readonly ZodIssue[];
    constructor(message: string, issues: readonly ZodIssue[]);
}
//# sourceMappingURL=errors.d.ts.map