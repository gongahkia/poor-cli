import { z } from "zod";
import { formatResponse, validateInput } from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import { getShieldAuditStore } from "../shield/audit-store.js";
import { scanToolCatalogForPoisoning } from "../shield/scanner.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const ShieldAuditLookupSchema = z.object({
  auditId: z.string().optional(),
  traceId: z.string().optional(),
  requestId: z.string().optional(),
  toolName: z.string().optional(),
  limit: z.number().int().min(1).max(100).optional(),
});

const toResult = (payload: unknown): ToolResult => ({
  content: [{ type: "text", text: formatResponse(payload as Record<string, unknown>, "json") }],
  structuredContent: payload as Readonly<Record<string, unknown>>,
});

const handleAuditLookup = async (input: unknown): Promise<ToolResult> => {
  const params = validateInput(ShieldAuditLookupSchema, input);
  const store = getShieldAuditStore();
  if (params.auditId !== undefined) {
    return toResult({ record: store.get(params.auditId), replay: store.getReplay(params.auditId) });
  }
  return toResult({
    records: store.query({
      ...(params.traceId === undefined ? {} : { traceId: params.traceId }),
      ...(params.requestId === undefined ? {} : { requestId: params.requestId }),
      ...(params.toolName === undefined ? {} : { toolName: params.toolName }),
      ...(params.limit === undefined ? {} : { limit: params.limit }),
    }),
  });
};

const handleToolScan = async (): Promise<ToolResult> => {
  const { ALL_TOOL_DEFINITIONS } = await import("./tool-set.js");
  const findings = scanToolCatalogForPoisoning(ALL_TOOL_DEFINITIONS);
  return toResult({ findings, scannedTools: ALL_TOOL_DEFINITIONS.length });
};

export const shieldToolDefinitions = [
  {
    name: "swee_shield_audit_lookup",
    description: "Look up Swee Shield audit records and replay metadata by audit, trace, request, or tool identifier.",
    surface: "canonical",
    inputSchema: ShieldAuditLookupSchema.shape,
    toolsets: ["ops"],
    handler: handleAuditLookup,
  },
  {
    name: "swee_shield_scan_tools",
    description: "Scan registered tool descriptions for MCP prompt-injection and poisoning warning patterns.",
    surface: "canonical",
    inputSchema: z.object({}).shape,
    toolsets: ["ops"],
    handler: handleToolScan,
  },
] as const satisfies readonly RegisteredToolDefinition[];
