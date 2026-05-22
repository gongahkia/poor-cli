import type { ShieldAuditRecord, ShieldPolicyDecision, ShieldToolMetadata, ToolResult } from "@swee-sg/shared";
import { evaluateShieldPolicy } from "./policy.js";
import { shieldAuditStore } from "./audit-store.js";

type ShieldedInvocation = {
  readonly toolName: string;
  readonly input: unknown;
  readonly metadata?: ShieldToolMetadata;
  readonly traceId?: string;
  readonly requestId?: string;
  readonly handler: (input: unknown) => Promise<ToolResult>;
};

const toDeniedResult = (decision: ShieldPolicyDecision, audit?: ShieldAuditRecord): ToolResult => ({
  isError: true,
  content: [{ type: "text", text: decision.message }],
  structuredContent: {
    error: {
      source: "swee-shield",
      tool: decision.toolName,
      code: "SWEE_SHIELD_DENIED",
      retryable: false,
      severity: "high",
      category: "policy",
      message: decision.message,
      suggestedAction: "Inspect swee://shield/policy and adjust the policy only if this call is intentionally allowed.",
      details: decision,
    },
    shield: {
      decision,
      ...(audit === undefined ? {} : { auditId: audit.auditId }),
    },
  },
});

export const invokeWithShield = async (params: ShieldedInvocation): Promise<ToolResult> => {
  const started = Date.now();
  const startedAt = new Date(started).toISOString();
  const decision = evaluateShieldPolicy({
    toolName: params.toolName,
    metadata: params.metadata,
  });

  if (decision.decision === "deny") {
    const finishedAt = new Date().toISOString();
    const audit = shieldAuditStore.record({
      traceId: params.traceId,
      requestId: params.requestId,
      toolName: params.toolName,
      decision,
      status: "denied",
      startedAt,
      finishedAt,
      durationMs: Date.now() - started,
      input: params.input,
    });
    return toDeniedResult(decision, audit);
  }

  try {
    const result = await params.handler(params.input);
    const audit = shieldAuditStore.record({
      traceId: params.traceId,
      requestId: params.requestId,
      toolName: params.toolName,
      decision,
      status: result.isError === true ? "error" : "success",
      startedAt,
      finishedAt: new Date().toISOString(),
      durationMs: Date.now() - started,
      input: params.input,
      output: result.structuredContent ?? result.content,
    });
    return {
      ...result,
      structuredContent: {
        ...(result.structuredContent ?? {}),
        shield: {
          decision,
          auditId: audit.auditId,
        },
      },
    };
  } catch (error) {
    const payload = {
      source: "swee-shield",
      tool: params.toolName,
      code: "TOOL_EXECUTION_FAILED",
      retryable: false,
      severity: "medium" as const,
      category: "tool_execution",
      message: error instanceof Error ? error.message : String(error),
    };
    const audit = shieldAuditStore.record({
      traceId: params.traceId,
      requestId: params.requestId,
      toolName: params.toolName,
      decision,
      status: "error",
      startedAt,
      finishedAt: new Date().toISOString(),
      durationMs: Date.now() - started,
      input: params.input,
      error: payload,
    });
    return {
      isError: true,
      content: [{ type: "text", text: payload.message }],
      structuredContent: {
        error: payload,
        shield: {
          decision,
          auditId: audit.auditId,
        },
      },
    };
  }
};
