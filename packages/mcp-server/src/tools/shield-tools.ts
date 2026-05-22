import { formatResponse } from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import { z } from "zod";
import { shieldAuditStore } from "../shield/audit-store.js";
import { evaluateShieldPolicy, loadShieldPolicy } from "../shield/policy.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const EvaluateSchema = z.object({
  toolName: z.string().min(1),
});

const AuditLookupSchema = z.object({
  id: z.string().min(1),
});

const AuditRecentSchema = z.object({
  limit: z.number().int().positive().max(500).optional(),
});

const jsonResult = (record: Readonly<Record<string, unknown>>): ToolResult => ({
  content: [{ type: "text", text: formatResponse(record, "json") }],
  structuredContent: { record },
});

export const shieldToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "swee_shield_policy",
    description: "Inspect the active Swee Shield policy mode and thresholds.",
    surface: "canonical",
    toolsets: ["public"],
    inputSchema: {},
    handler: async () => jsonResult(loadShieldPolicy() as unknown as Readonly<Record<string, unknown>>),
  },
  {
    name: "swee_shield_evaluate",
    description: "Evaluate whether Swee Shield would allow, warn, or deny a tool call.",
    surface: "canonical",
    toolsets: ["public"],
    inputSchema: EvaluateSchema.shape,
    handler: async (input) => {
      const parsed = EvaluateSchema.parse(input);
      return jsonResult(evaluateShieldPolicy({ toolName: parsed.toolName }) as unknown as Readonly<Record<string, unknown>>);
    },
  },
  {
    name: "swee_shield_audit_lookup",
    description: "Look up a Swee Shield audit record by audit ID, trace ID, or request ID.",
    surface: "canonical",
    toolsets: ["public"],
    inputSchema: AuditLookupSchema.shape,
    handler: async (input) => {
      const parsed = AuditLookupSchema.parse(input);
      const record = shieldAuditStore.get(parsed.id);
      return jsonResult({ record });
    },
  },
  {
    name: "swee_shield_audit_recent",
    description: "List recent Swee Shield audit records.",
    surface: "canonical",
    toolsets: ["public"],
    inputSchema: AuditRecentSchema.shape,
    handler: async (input) => {
      const parsed = AuditRecentSchema.parse(input ?? {});
      return jsonResult({ records: shieldAuditStore.recent(parsed.limit) });
    },
  },
];
