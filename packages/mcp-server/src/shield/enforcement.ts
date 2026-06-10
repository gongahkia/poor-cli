import type { RegisteredToolDefinition } from "../tools/tool-definition.js";
import type { ShieldAuditRecord, ToolErrorPayload, ToolResult } from "@swee-sg/shared";
import { buildShieldToolMetadata, evaluateShieldPolicy } from "./policy.js";
import { getShieldAuditStore } from "./audit-store.js";
import {
  hasBlockingRuntimeFinding,
  resolveRuntimeScanMode,
  RuntimeScanBlockedError,
  scanToolResultForRuntimeFindings,
} from "./runtime-scanner.js";

export class ShieldDeniedError extends Error {
  constructor(readonly audit: ShieldAuditRecord) {
    super(audit.decision.message);
    this.name = "ShieldDeniedError";
  }
}

const toToolError = (toolName: string, error: unknown): ToolErrorPayload => {
  if (error instanceof RuntimeScanBlockedError) {
    return {
      source: "swee-shield",
      tool: toolName,
      code: "RUNTIME_SCAN_BLOCKED",
      retryable: false,
      severity: "high",
      category: "runtime_scan",
      message: error.message,
      details: { findings: error.findings },
    };
  }

  return {
    source: "swee-shield",
    tool: toolName,
    code: error instanceof ShieldDeniedError ? "SHIELD_DENIED" : "TOOL_INVOCATION_FAILED",
    retryable: false,
    severity: error instanceof ShieldDeniedError ? "high" : "medium",
    category: error instanceof ShieldDeniedError ? "policy" : "runtime",
    message: error instanceof Error ? error.message : String(error),
  };
};

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
    const rawOutput = result.structuredContent ?? result.content;
    const runtimeScan = scanToolResultForRuntimeFindings(result);
    if (resolveRuntimeScanMode() === "block" && hasBlockingRuntimeFinding(runtimeScan.findings)) {
      throw new RuntimeScanBlockedError(runtimeScan.findings, rawOutput);
    }
    const scannedResult = runtimeScan.result;
    const finishedAt = new Date().toISOString();
    const audit = getShieldAuditStore().record({
      ...(context.traceId === undefined ? {} : { traceId: context.traceId }),
      ...(context.requestId === undefined ? {} : { requestId: context.requestId }),
      toolName: tool.name,
      decision,
      status: scannedResult.isError === true ? "error" : "success",
      startedAt,
      finishedAt,
      durationMs: Date.now() - started,
      input,
      output: scannedResult.structuredContent ?? scannedResult.content,
      rawOutput,
      runtimeFindings: runtimeScan.findings,
    });
    return {
      ...scannedResult,
      structuredContent: {
        ...(scannedResult.structuredContent ?? {}),
        shield: { decision, auditId: audit.auditId },
      },
      _meta: {
        ...(scannedResult._meta ?? {}),
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
      ...(error instanceof RuntimeScanBlockedError
        ? { rawOutput: error.rawOutput, runtimeFindings: error.findings }
        : {}),
      error: toToolError(tool.name, error),
    });
    const throwable = error instanceof Error ? error : new Error(String(error));
    Object.assign(throwable, { shieldAudit: audit });
    throw throwable;
  }
};
