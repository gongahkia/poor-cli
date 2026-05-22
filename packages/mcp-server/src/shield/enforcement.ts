import type { RegisteredToolDefinition } from "../tools/tool-definition.js";
import type { ShieldAuditRecord, ToolErrorPayload, ToolResult } from "@swee-sg/shared";
import { buildShieldToolMetadata, evaluateShieldPolicy } from "./policy.js";
import { getShieldAuditStore } from "./audit-store.js";

export class ShieldDeniedError extends Error {
  constructor(readonly audit: ShieldAuditRecord) {
    super(audit.decision.message);
    this.name = "ShieldDeniedError";
  }
}

const toToolError = (toolName: string, error: unknown): ToolErrorPayload => ({
  source: "swee-shield",
  tool: toolName,
  code: error instanceof ShieldDeniedError ? "SHIELD_DENIED" : "TOOL_INVOCATION_FAILED",
  retryable: false,
  severity: error instanceof ShieldDeniedError ? "high" : "medium",
  category: error instanceof ShieldDeniedError ? "policy" : "runtime",
  message: error instanceof Error ? error.message : String(error),
});

export const invokeShieldedTool = async (
  tool: RegisteredToolDefinition,
  input: unknown,
  context: { readonly traceId?: string; readonly requestId?: string } = {},
): Promise<ToolResult & { readonly shieldAudit: ShieldAuditRecord }> => {
  const started = Date.now();
  const startedAt = new Date(started).toISOString();
  const decision = evaluateShieldPolicy({
    toolName: tool.name,
    metadata: buildShieldToolMetadata(tool),
  });

  if (decision.decision === "deny") {
    const finishedAt = new Date().toISOString();
    const audit = getShieldAuditStore().record({
      ...(context.traceId === undefined ? {} : { traceId: context.traceId }),
      ...(context.requestId === undefined ? {} : { requestId: context.requestId }),
      toolName: tool.name,
      decision,
      status: "denied",
      startedAt,
      finishedAt,
      durationMs: Date.now() - started,
      input,
    });
    return {
      content: [{ type: "text", text: decision.message }],
      isError: true,
      structuredContent: { shield: { decision, auditId: audit.auditId } },
      _meta: { "swee/shield": { decision, auditId: audit.auditId } },
      shieldAudit: audit,
    };
  }

  try {
    const result = await tool.handler(input);
    const finishedAt = new Date().toISOString();
    const audit = getShieldAuditStore().record({
      ...(context.traceId === undefined ? {} : { traceId: context.traceId }),
      ...(context.requestId === undefined ? {} : { requestId: context.requestId }),
      toolName: tool.name,
      decision,
      status: result.isError === true ? "error" : "success",
      startedAt,
      finishedAt,
      durationMs: Date.now() - started,
      input,
      output: result.structuredContent ?? result.content,
    });
    return {
      ...result,
      structuredContent: {
        ...(result.structuredContent ?? {}),
        shield: { decision, auditId: audit.auditId },
      },
      _meta: {
        ...(result._meta ?? {}),
        "swee/shield": { decision, auditId: audit.auditId },
      },
      shieldAudit: audit,
    };
  } catch (error) {
    const finishedAt = new Date().toISOString();
    const audit = getShieldAuditStore().record({
      ...(context.traceId === undefined ? {} : { traceId: context.traceId }),
      ...(context.requestId === undefined ? {} : { requestId: context.requestId }),
      toolName: tool.name,
      decision,
      status: "error",
      startedAt,
      finishedAt,
      durationMs: Date.now() - started,
      input,
      error: toToolError(tool.name, error),
    });
    const throwable = error instanceof Error ? error : new Error(String(error));
    Object.assign(throwable, { shieldAudit: audit });
    throw throwable;
  }
};
