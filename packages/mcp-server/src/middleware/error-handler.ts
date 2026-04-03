import { createLogger, ApiError, ValidationError } from "@sg-apis/shared";
import type { ToolErrorPayload, ToolResult } from "@sg-apis/shared";

const logger = createLogger("error-handler");

type ToolHandler = (input: unknown) => Promise<ToolResult>;

const CREDENTIAL_HINTS: Record<string, string> = {
  onemap: "Fix: export SG_API_ONEMAP_EMAIL=<email> SG_API_ONEMAP_PASSWORD=<pass>, or: sg-data init --onemap-email <email> --onemap-password <pass>",
  ura: "Fix: export SG_API_URA_KEY=<key>, or: sg-data init --ura-key <key>",
  lta: "Fix: export SG_API_LTA_KEY=<key>, or: sg-data init --lta-key <key>",
};

const enrichCredentialAction = (source: string, statusCode?: number): string | undefined => {
  if (statusCode !== 401 && statusCode !== 403) return undefined;
  const key = source.toLowerCase().replace(/\s+/g, "");
  if (key.includes("onemap")) return CREDENTIAL_HINTS["onemap"];
  if (key.includes("ura")) return CREDENTIAL_HINTS["ura"];
  if (key.includes("lta")) return CREDENTIAL_HINTS["lta"];
  return undefined;
};

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
    const credHint = enrichCredentialAction(error.source, error.statusCode);
    const action = credHint ?? error.suggestedAction;
    return {
      source: error.source,
      tool: error.tool ?? tool,
      code: error.code,
      retryable: error.retryable,
      message: error.message,
      ...(action !== undefined ? { suggestedAction: action } : {}),
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
