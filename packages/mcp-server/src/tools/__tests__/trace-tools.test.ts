import { ApiError } from "@dude/shared";
import { beforeEach, describe, expect, it } from "vitest";
import {
  clearToolInvocationAuditStoreForTests,
  recordToolInvocationAudit,
} from "../../middleware/request-audit.js";
import { handleRequestLookup, handleTraceLookup } from "../trace-tools.js";

describe("trace lookup tools", () => {
  beforeEach(() => {
    clearToolInvocationAuditStoreForTests();
  });

  it("returns the matching invocation for sg_trace_lookup", async () => {
    const finishedAt = new Date().toISOString();
    recordToolInvocationAudit({
      traceId: "11111111-1111-4111-8111-111111111111",
      requestId: "22222222-2222-4222-8222-222222222222",
      tool: "sg_config_get",
      status: "success",
      startedAt: finishedAt,
      finishedAt,
      durationMs: 10,
    });

    const result = await handleTraceLookup({
      traceId: "11111111-1111-4111-8111-111111111111",
      format: "json",
    });
    const payload = result.structuredContent as Record<string, unknown>;
    expect(payload["found"]).toBe(true);
    expect(payload["lookupType"]).toBe("traceId");
    expect(payload["query"]).toBe("11111111-1111-4111-8111-111111111111");
    const invocation = payload["invocation"] as Record<string, unknown>;
    expect(invocation["tool"]).toBe("sg_config_get");
    expect(invocation["status"]).toBe("success");
    const auditStore = payload["auditStore"] as Record<string, unknown>;
    expect(auditStore["recordCount"]).toBe(1);
    expect(typeof auditStore["maxEntries"]).toBe("number");
    expect(typeof auditStore["retentionSeconds"]).toBe("number");
  });

  it("throws REQUEST_NOT_FOUND for missing request IDs", async () => {
    await expect(async () => {
      await handleRequestLookup({
        requestId: "33333333-3333-4333-8333-333333333333",
        format: "json",
      });
    }).rejects.toMatchObject({
      name: "ApiError",
      code: "REQUEST_NOT_FOUND",
      retryable: false,
      statusCode: 404,
    } satisfies Partial<ApiError>);
  });
});
