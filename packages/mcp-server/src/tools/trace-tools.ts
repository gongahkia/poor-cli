import { ApiError, formatResponse, resolveOutputFormat, validateInput } from "@dude/shared";
import type { ToolResult } from "@dude/shared";
import { z } from "zod";
import {
  getToolInvocationAuditByRequestId,
  getToolInvocationAuditStats,
  getToolInvocationAuditByTraceId,
  listRecentToolInvocationAudits,
} from "../middleware/request-audit.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const TraceLookupSchema = z.object({
  traceId: z.string().uuid(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

const RequestLookupSchema = z.object({
  requestId: z.string().uuid(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

const toLookupResult = (payload: Readonly<Record<string, unknown>>, format: "json" | "markdown"): ToolResult => {
  const text = formatResponse(payload, format);
  return {
    content: [{ type: "text", text }],
    structuredContent: payload,
  };
};

export const handleTraceLookup = async (
  input: Readonly<{ traceId: string; format?: "json" | "markdown" | undefined }>,
): Promise<ToolResult> => {
  const resolved = validateInput(TraceLookupSchema, input);
  const record = getToolInvocationAuditByTraceId(resolved.traceId);
  if (record === null) {
    throw new ApiError({
      apiName: "trace-audit",
      source: "audit-index",
      statusCode: 404,
      code: "TRACE_NOT_FOUND",
      message: `No local audit record found for traceId ${resolved.traceId}.`,
      retryable: false,
      suggestedAction: "Run the target call again and query sg_trace_lookup with the returned traceId.",
    });
  }

  const format = resolveOutputFormat(resolved.format) === "json" ? "json" : "markdown";
  return toLookupResult(
    {
      lookupType: "traceId",
      query: resolved.traceId,
      found: true,
      invocation: record as unknown as Record<string, unknown>,
      recent: listRecentToolInvocationAudits(5) as unknown as Record<string, unknown>[],
      auditStore: getToolInvocationAuditStats() as unknown as Record<string, unknown>,
    },
    format,
  );
};

export const handleRequestLookup = async (
  input: Readonly<{ requestId: string; format?: "json" | "markdown" | undefined }>,
): Promise<ToolResult> => {
  const resolved = validateInput(RequestLookupSchema, input);
  const record = getToolInvocationAuditByRequestId(resolved.requestId);
  if (record === null) {
    throw new ApiError({
      apiName: "trace-audit",
      source: "audit-index",
      statusCode: 404,
      code: "REQUEST_NOT_FOUND",
      message: `No local audit record found for requestId ${resolved.requestId}.`,
      retryable: false,
      suggestedAction: "Run the target call again and query sg_request_lookup with the returned requestId.",
    });
  }

  const format = resolveOutputFormat(resolved.format) === "json" ? "json" : "markdown";
  return toLookupResult(
    {
      lookupType: "requestId",
      query: resolved.requestId,
      found: true,
      invocation: record as unknown as Record<string, unknown>,
      recent: listRecentToolInvocationAudits(5) as unknown as Record<string, unknown>[],
      auditStore: getToolInvocationAuditStats() as unknown as Record<string, unknown>,
    },
    format,
  );
};

export const traceToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_trace_lookup",
    description: "Look up a local tool invocation audit record by traceId.",
    surface: "operational",
    inputSchema: TraceLookupSchema.shape,
    handler: async (input: unknown) =>
      handleTraceLookup(input as Parameters<typeof handleTraceLookup>[0]),
  },
  {
    name: "sg_request_lookup",
    description: "Look up a local tool invocation audit record by requestId.",
    surface: "operational",
    inputSchema: RequestLookupSchema.shape,
    handler: async (input: unknown) =>
      handleRequestLookup(input as Parameters<typeof handleRequestLookup>[0]),
  },
];
