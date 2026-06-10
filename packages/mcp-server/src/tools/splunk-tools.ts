import { z } from "zod";
import { ApiError, formatResponse, resolveOutputFormat, validateInput } from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { callSplunkTool } from "../upstreams/splunk/mcp-client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const SPLUNK_PROXY_UPSTREAM_TOOLS = {
  search: "splunk_search",
  listIndexes: "splunk_list_indexes",
  listSavedSearches: "splunk_list_saved_searches",
} as const;

const SplunkFormatSchema = {
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
};

const SplunkSearchSchema = z.object({
  query: z.string().min(1),
  index: z.string().min(1).optional(),
  earliest: z.string().min(1).optional(),
  latest: z.string().min(1).optional(),
  limit: z.number().int().min(1).max(100).optional(),
  ...SplunkFormatSchema,
});

const SplunkListSchema = z.object({
  filter: z.string().min(1).max(120).optional(),
  limit: z.number().int().min(1).max(100).optional(),
  ...SplunkFormatSchema,
});

type SplunkSearchInput = z.infer<typeof SplunkSearchSchema>;

const DISALLOWED_SPL = /\b(delete|outputlookup|collect|sendemail|script|map)\b/i;

const deny = (message: string, details?: unknown): ApiError =>
  new ApiError({
    apiName: "splunk_mcp",
    source: "Swee Shield Splunk Proxy",
    statusCode: 400,
    code: "SPLUNK_PROXY_DENIED",
    message,
    retryable: false,
    details,
  });

const allowedIndexes = (): readonly string[] => (
  process.env["SPLUNK_MCP_ALLOWED_INDEXES"] ?? ""
)
  .split(",")
  .map((value) => value.trim())
  .filter((value) => value !== "");

const queryIndexes = (query: string): readonly string[] =>
  Array.from(query.matchAll(/\bindex\s*=\s*([A-Za-z0-9_.-]+)/gi))
    .map((match) => match[1])
    .filter((value): value is string => value !== undefined && value.trim() !== "");

const assertSearchAllowed = (params: SplunkSearchInput): void => {
  if (DISALLOWED_SPL.test(params.query)) {
    throw deny("Splunk search contains a command blocked by the Swee Shield proxy.", { reason: "destructive_or_exfiltration_spl" });
  }
  const indexes = allowedIndexes();
  const requestedIndexes = new Set([
    ...queryIndexes(params.query),
    ...(params.index === undefined ? [] : [params.index]),
  ]);
  for (const index of requestedIndexes) {
    if (indexes.length > 0 && !indexes.includes(index)) {
      throw deny("Splunk search index is not allowlisted for this proxy.", { index, allowedIndexes: indexes });
    }
  }
};

const toResult = (payload: unknown, format: OutputFormat, upstreamToolName: string): ToolResult => ({
  content: [{ type: "text", text: formatResponse(payload as Record<string, unknown>, format) }],
  structuredContent: {
    upstreamToolName,
    observedAt: new Date().toISOString(),
    result: payload,
  },
});

const handleSplunkSearch = async (input: unknown): Promise<ToolResult> => {
  const params = validateInput(SplunkSearchSchema, input);
  assertSearchAllowed(params);
  const limit = params.limit ?? 50;
  const payload = await callSplunkTool(SPLUNK_PROXY_UPSTREAM_TOOLS.search, {
    query: params.query,
    ...(params.index === undefined ? {} : { index: params.index }),
    ...(params.earliest === undefined ? {} : { earliest: params.earliest }),
    ...(params.latest === undefined ? {} : { latest: params.latest }),
    limit,
  });
  return toResult(payload, resolveOutputFormat(params.format), SPLUNK_PROXY_UPSTREAM_TOOLS.search);
};

const handleSplunkList = async (
  input: unknown,
  upstreamToolName: typeof SPLUNK_PROXY_UPSTREAM_TOOLS.listIndexes | typeof SPLUNK_PROXY_UPSTREAM_TOOLS.listSavedSearches,
): Promise<ToolResult> => {
  const params = validateInput(SplunkListSchema, input);
  const payload = await callSplunkTool(upstreamToolName, {
    ...(params.filter === undefined ? {} : { filter: params.filter }),
    limit: params.limit ?? 100,
  });
  return toResult(payload, resolveOutputFormat(params.format), upstreamToolName);
};

export const splunkToolDefinitions = [
  {
    name: "splunk_search",
    description: "Run a bounded read-only SPL search through the Swee Shield-governed Splunk MCP proxy.",
    surface: "operational",
    inputSchema: SplunkSearchSchema.shape,
    toolsets: ["ops"],
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true,
    },
    handler: handleSplunkSearch,
  },
  {
    name: "splunk_list_indexes",
    description: "List Splunk indexes through the Swee Shield-governed Splunk MCP proxy.",
    surface: "operational",
    inputSchema: SplunkListSchema.shape,
    toolsets: ["ops"],
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    handler: (input) => handleSplunkList(input, SPLUNK_PROXY_UPSTREAM_TOOLS.listIndexes),
  },
  {
    name: "splunk_list_saved_searches",
    description: "List Splunk saved searches through the Swee Shield-governed Splunk MCP proxy.",
    surface: "operational",
    inputSchema: SplunkListSchema.shape,
    toolsets: ["ops"],
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    handler: (input) => handleSplunkList(input, SPLUNK_PROXY_UPSTREAM_TOOLS.listSavedSearches),
  },
] as const satisfies readonly RegisteredToolDefinition[];
