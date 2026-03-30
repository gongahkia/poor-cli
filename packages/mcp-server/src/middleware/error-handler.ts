import { createLogger, ApiError, ValidationError } from "@sg-apis/shared";
import type { ToolErrorPayload, ToolResult } from "@sg-apis/shared";

const logger = createLogger("error-handler");

type ToolHandler = (input: unknown) => Promise<ToolResult>;

const formatErrorText = (payload: ToolErrorPayload): string => {
  const retryHint = payload.retryable ? "Yes" : "No";
  const lines = [
    `Tool ${payload.tool} failed.`,
    `Source: ${payload.source}`,
    `Code: ${payload.code}`,
    `Retryable: ${retryHint}`,
    `Message: ${payload.message}`,
  ];

  if (payload.suggestedAction !== undefined) {
    lines.push(`Suggested action: ${payload.suggestedAction}`);
  }

  return lines.join("\n");
};

const logHandledToolError = (payload: ToolErrorPayload): void => {
  const level = payload.code === "VALIDATION_ERROR"
    ? "warn"
    : payload.retryable
      ? "warn"
      : "error";
  logger[level]("tool invocation failed", {
    tool: payload.tool,
    source: payload.source,
    code: payload.code,
    retryable: payload.retryable,
    statusCode: payload.statusCode,
    message: payload.message,
    ...(payload.suggestedAction === undefined ? {} : { suggestedAction: payload.suggestedAction }),
  });
};

export const toToolErrorPayload = (error: unknown, tool: string): ToolErrorPayload => {
  if (error instanceof ValidationError) {
    return {
      source: "validation",
      tool,
      code: "VALIDATION_ERROR",
      retryable: false,
      message: error.message,
      suggestedAction: "Check the tool input schema and resend valid parameters.",
      statusCode: 400,
      details: error.issues,
    };
  }

  if (error instanceof ApiError) {
    return {
      source: error.source,
      tool: error.tool ?? tool,
      code: error.code,
      retryable: error.retryable,
      message: error.message,
      ...(error.suggestedAction !== undefined ? { suggestedAction: error.suggestedAction } : {}),
      statusCode: error.statusCode,
      ...(error.details === undefined ? {} : { details: error.details }),
    };
  }

  logger.error("unhandled error", {
    tool,
    error: error instanceof Error ? error.message : String(error),
  });

  return {
    source: "internal",
    tool,
    code: "INTERNAL_ERROR",
    retryable: false,
    message: "Internal error. Check server logs.",
    suggestedAction: "Inspect server logs and retry the tool call.",
    statusCode: 500,
  };
};

export const wrapHandler = (tool: string, handler: ToolHandler): ToolHandler => {
  return async (input: unknown): Promise<ToolResult> => {
    try {
      return await handler(input);
    } catch (error) {
      const payload = toToolErrorPayload(error, tool);
      logHandledToolError(payload);
      return {
        isError: true,
        content: [{ type: "text", text: formatErrorText(payload) }],
        structuredContent: {
          error: payload,
        },
      };
    }
  };
};
