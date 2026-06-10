import { z } from "zod";
import { formatResponse, validateInput } from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import { getShieldApprovalStore } from "../shield/approval-store.js";
import { getShieldAuditStore } from "../shield/audit-store.js";
import { scanToolCatalogForPoisoning } from "../shield/scanner.js";
import { buildSplunkRedTeamMatrix, simulateSplunkSearchPolicy } from "../shield/splunk-policy-simulator.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const ShieldAuditLookupSchema = z.object({
  auditId: z.string().optional(),
  traceId: z.string().optional(),
  requestId: z.string().optional(),
  toolName: z.string().optional(),
  limit: z.number().int().min(1).max(100).optional(),
});

const ShieldApprovalListSchema = z.object({
  status: z.enum(["pending", "approved", "rejected", "expired"]).optional(),
  toolName: z.string().optional(),
  limit: z.number().int().min(1).max(100).optional(),
});

const ShieldApprovalDecideSchema = z.object({
  approvalId: z.string().uuid(),
  decision: z.enum(["approved", "rejected"]),
  reviewer: z.string().min(1).max(120).optional(),
  comment: z.string().max(500).optional(),
});

const ShieldPolicySimulateSchema = z.object({
  query: z.string().min(1),
  index: z.string().min(1).optional(),
  earliest: z.string().min(1).optional(),
  latest: z.string().min(1).optional(),
  limit: z.number().int().min(1).max(100).optional(),
});

const RuntimeFindingOutputSchema = z.object({
  severity: z.string(),
  code: z.string(),
  action: z.string(),
}).passthrough();

const ShieldDecisionOutputSchema = z.object({
  decision: z.string(),
  riskLevel: z.string(),
  reasonCodes: z.array(z.string()).optional(),
}).passthrough();

const ShieldAuditRecordOutputSchema = z.object({
  auditId: z.string(),
  toolName: z.string(),
  status: z.string(),
  startedAt: z.string(),
  finishedAt: z.string().optional(),
  durationMs: z.number(),
  inputHash: z.string(),
  outputHash: z.string().nullable(),
  rawOutputHash: z.string().nullable(),
  runtimeFindings: z.array(RuntimeFindingOutputSchema),
  decision: ShieldDecisionOutputSchema,
}).passthrough();

const ShieldAuditLookupOutputSchema = z.object({
  record: ShieldAuditRecordOutputSchema.nullable().optional(),
  replay: z.unknown().optional(),
  records: z.array(ShieldAuditRecordOutputSchema).optional(),
}).passthrough();

const ApprovalRecordOutputSchema = z.object({
  approvalId: z.string(),
  toolName: z.string(),
  status: z.enum(["pending", "approved", "rejected", "expired"]),
  createdAt: z.string(),
  expiresAt: z.string(),
  requestHash: z.string(),
  request: z.unknown(),
  risk: z.unknown(),
  decision: z.unknown(),
}).passthrough();

const ApprovalListOutputSchema = z.object({
  records: z.array(ApprovalRecordOutputSchema),
}).passthrough();

const PolicySimulationOutputSchema = z.object({
  simulation: z.object({
    status: z.enum(["allow", "approval_required", "deny"]),
    riskScore: z.number(),
    severity: z.string(),
    ruleCodes: z.array(z.string()),
    suggestedSaferQuery: z.string(),
  }).passthrough(),
  redTeamMatrix: z.array(z.unknown()),
}).passthrough();

const toResult = (payload: unknown): ToolResult => ({
  content: [{ type: "text", text: formatResponse(payload as Record<string, unknown>, "json") }],
  structuredContent: payload as Readonly<Record<string, unknown>>,
});

const toPolicyInput = (params: z.infer<typeof ShieldPolicySimulateSchema>) => ({
  query: params.query,
  ...(params.index === undefined ? {} : { index: params.index }),
  ...(params.earliest === undefined ? {} : { earliest: params.earliest }),
  ...(params.latest === undefined ? {} : { latest: params.latest }),
  ...(params.limit === undefined ? {} : { limit: params.limit }),
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

const handleApprovalList = async (input: unknown): Promise<ToolResult> => {
  const params = validateInput(ShieldApprovalListSchema, input);
  return toResult({
    records: getShieldApprovalStore().list({
      ...(params.status === undefined ? {} : { status: params.status }),
      ...(params.toolName === undefined ? {} : { toolName: params.toolName }),
      ...(params.limit === undefined ? {} : { limit: params.limit }),
    }),
  });
};

const handleApprovalDecide = async (input: unknown): Promise<ToolResult> => {
  const params = validateInput(ShieldApprovalDecideSchema, input);
  return toResult({
    record: getShieldApprovalStore().decide({
      approvalId: params.approvalId,
      decision: params.decision,
      ...(params.reviewer === undefined ? {} : { reviewer: params.reviewer }),
      ...(params.comment === undefined ? {} : { comment: params.comment }),
    }),
  });
};

const handlePolicySimulate = async (input: unknown): Promise<ToolResult> => {
  const params = validateInput(ShieldPolicySimulateSchema, input);
  const simulation = simulateSplunkSearchPolicy(toPolicyInput(params));
  return toResult({
    simulation,
    redTeamMatrix: buildSplunkRedTeamMatrix(),
  });
};

export const shieldToolDefinitions = [
  {
    name: "swee_shield_audit_lookup",
    description: "Look up Swee Shield audit records and replay metadata by audit, trace, request, or tool identifier.",
    surface: "canonical",
    inputSchema: ShieldAuditLookupSchema.shape,
    outputSchema: ShieldAuditLookupOutputSchema,
    toolsets: ["ops"],
    handler: handleAuditLookup,
  },
  {
    name: "swee_shield_scan_tools",
    description: "Scan registered tool descriptions for MCP prompt-injection and poisoning warning patterns.",
    surface: "canonical",
    inputSchema: z.object({}).shape,
    outputSchema: z.object({
      findings: z.array(z.unknown()),
      scannedTools: z.number(),
    }).passthrough(),
    toolsets: ["ops"],
    handler: handleToolScan,
  },
  {
    name: "swee_shield_approval_list",
    description: "List Swee Shield human approval requests for risky Splunk proxy actions.",
    surface: "canonical",
    inputSchema: ShieldApprovalListSchema.shape,
    outputSchema: ApprovalListOutputSchema,
    toolsets: ["ops"],
    handler: handleApprovalList,
  },
  {
    name: "swee_shield_approval_decide",
    description: "Approve or reject a pending Swee Shield approval request for a risky Splunk proxy action.",
    surface: "canonical",
    inputSchema: ShieldApprovalDecideSchema.shape,
    outputSchema: z.object({ record: ApprovalRecordOutputSchema }).passthrough(),
    toolsets: ["ops"],
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false,
    },
    handler: handleApprovalDecide,
  },
  {
    name: "swee_shield_policy_simulate",
    description: "Simulate Swee Shield Splunk proxy policy decisions against a candidate SPL query and red-team corpus without calling Splunk.",
    surface: "canonical",
    inputSchema: ShieldPolicySimulateSchema.shape,
    outputSchema: PolicySimulationOutputSchema,
    toolsets: ["ops"],
    handler: handlePolicySimulate,
  },
] as const satisfies readonly RegisteredToolDefinition[];
