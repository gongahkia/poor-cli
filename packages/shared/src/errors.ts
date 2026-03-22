import type { ZodIssue } from "zod";

export class ApiError extends Error {
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
  }) {
    super(params.message);
    this.name = "ApiError";
    this.apiName = params.apiName;
    this.statusCode = params.statusCode;
    this.retryable = params.retryable;
    this.details = params.details;
  }
}

export class ValidationError extends Error {
  readonly field?: string;
  readonly issues: readonly ZodIssue[];

  constructor(message: string, issues: readonly ZodIssue[]) {
    super(message);
    this.name = "ValidationError";
    this.issues = issues;
  }
}
