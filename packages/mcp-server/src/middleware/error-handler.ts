import { randomUUID } from "node:crypto";
import { createLogger, ApiError, ValidationError } from "@sg-apis/shared";
import type { ContextIds, ToolErrorPayload, ToolResult } from "@sg-apis/shared";
import { OPS_TAXONOMY_CATALOG } from "../ops-taxonomy.js";

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

type OpsTaxonomyEntry = (typeof OPS_TAXONOMY_CATALOG.errorCodes)[number];

const OPS_TAXONOMY_BY_CODE = new Map<string, OpsTaxonomyEntry>(
  OPS_TAXONOMY_CATALOG.errorCodes.map((entry) => [entry.code, entry]),
);

const inferHttpTaxonomy = (code: string, statusCode?: number): OpsTaxonomyEntry | null => {
  const matched = /^HTTP_(\d{3})$/.exec(code);
  if (matched === null) {
    return null;
  }

  const statusFragment = matched[1];
  if (statusFragment === undefined) {
    return null;
  }
  const numericStatus = Number.parseInt(statusFragment, 10);
  if (numericStatus === 429) {
    return OPS_TAXONOMY_BY_CODE.get("HTTP_429") ?? null;
  }

  if (numericStatus >= 500 || statusCode === 0) {
    return OPS_TAXONOMY_BY_CODE.get("HTTP_5XX") ?? null;
  }

  if (numericStatus >= 400) {
    return OPS_TAXONOMY_BY_CODE.get("HTTP_4XX") ?? null;
  }

  return null;
};

const withOpsTaxonomy = <T extends ToolErrorPayload>(payload: T): T => {
  const matched = OPS_TAXONOMY_BY_CODE.get(payload.code) ?? inferHttpTaxonomy(payload.code, payload.statusCode);
  if (matched === null || matched === undefined) {
    return payload;
  }

  return {
    ...payload,
    ...(payload.severity === undefined ? { severity: matched.severity } : {}),
    ...(payload.category === undefined ? { category: matched.category } : {}),
    ...(payload.suggestedAction === undefined ? { suggestedAction: matched.suggestedAction } : {}),
  };
};

const formatErrorText = (payload: ToolErrorPayload): string => {
  const retryHint = payload.retryable ? "Yes" : "No";
  const lines = [
    `Tool ${payload.tool} failed.`,
    `Source: ${payload.source}`,
    `Code: ${payload.code}`,
    ...(payload.category === undefined ? [] : [`Category: ${payload.category}`]),
    ...(payload.severity === undefined ? [] : [`Severity: ${payload.severity}`]),
    `Retryable: ${retryHint}`,
    `Message: ${payload.message}`,
  ];

  if (payload.suggestedAction !== undefined) {
    lines.push(`Suggested action: ${payload.suggestedAction}`);
  }
  if (payload.contextIds !== undefined) {
    lines.push(`Trace ID: ${payload.contextIds.traceId}`);
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
    ...(payload.category === undefined ? {} : { category: payload.category }),
    ...(payload.severity === undefined ? {} : { severity: payload.severity }),
    retryable: payload.retryable,
    statusCode: payload.statusCode,
    message: payload.message,
    ...(payload.contextIds === undefined ? {} : payload.contextIds),
    ...(payload.suggestedAction === undefined ? {} : { suggestedAction: payload.suggestedAction }),
  });
};

type ToolErrorContext = {
  readonly contextIds?: ContextIds;
};

export const toToolErrorPayload = (
  error: unknown,
  tool: string,
  context: ToolErrorContext = {},
): ToolErrorPayload => {
  const withContextIdsAndTaxonomy = <T extends ToolErrorPayload>(payload: T): T => {
    const withContextIds = context.contextIds === undefined
      ? payload
      : { ...payload, contextIds: context.contextIds };
    return withOpsTaxonomy(withContextIds);
  };

  if (error instanceof ValidationError) {
    return withContextIdsAndTaxonomy({
      source: "validation",
      tool,
      code: "VALIDATION_ERROR",
      retryable: false,
      message: error.message,
      suggestedAction: "Check the tool input schema and resend valid parameters.",
      statusCode: 400,
      details: error.issues,
    });
  }

  if (error instanceof ApiError) {
    const credHint = enrichCredentialAction(error.source, error.statusCode);
    const action = credHint ?? error.suggestedAction;
    return withContextIdsAndTaxonomy({
      source: error.source,
      tool: error.tool ?? tool,
      code: error.code,
      retryable: error.retryable,
      message: error.message,
      ...(action !== undefined ? { suggestedAction: action } : {}),
      statusCode: error.statusCode,
      ...(error.details === undefined ? {} : { details: error.details }),
    });
  }

  logger.error("unhandled error", {
    tool,
    error: error instanceof Error ? error.message : String(error),
  });

  return withContextIdsAndTaxonomy({
    source: "internal",
    tool,
    code: "INTERNAL_ERROR",
    retryable: false,
    message: "Internal error. Check server logs.",
    suggestedAction: "Inspect server logs and retry the tool call.",
    statusCode: 500,
  });
};

export const wrapHandler = (tool: string, handler: ToolHandler): ToolHandler => {
  return async (input: unknown): Promise<ToolResult> => {
    const requestId = randomUUID();
    const contextIds = {
      traceId: requestId,
      requestId,
    } as const;
    try {
      return await handler(input);
    } catch (error) {
      const payload = toToolErrorPayload(error, tool, { contextIds });
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
