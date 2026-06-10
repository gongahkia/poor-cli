import type { ZodIssue } from "zod";

export class ApiError extends Error {
  readonly apiName: string;
  readonly source: string;
  readonly statusCode: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly tool?: string;
  readonly suggestedAction?: string;
  readonly details?: unknown;

  constructor(params: {
    apiName: string;
    statusCode: number;
    message: string;
    retryable: boolean;
    source?: string;
    code?: string;
    tool?: string;
    suggestedAction?: string;
    details?: unknown;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.apiName = params.apiName;
    this.source = params.source ?? params.apiName;
    this.statusCode = params.statusCode;
    this.code = params.code ?? `HTTP_${params.statusCode}`;
    this.retryable = params.retryable;
    if (params.tool !== undefined) {
      this.tool = params.tool;
    }
    if (params.suggestedAction !== undefined) {
      this.suggestedAction = params.suggestedAction;
    }
    if (params.details !== undefined) {
      this.details = params.details;
    }
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
