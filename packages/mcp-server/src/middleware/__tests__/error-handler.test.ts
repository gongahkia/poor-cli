import { ApiError, ValidationError } from "@swee-sg/shared";
import { describe, expect, it } from "vitest";
import { toToolErrorPayload, wrapHandler } from "../error-handler.js";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

describe("error handler tracing", () => {
  it("attaches contextIds to wrapped tool errors", async () => {
    const handler = wrapHandler("sg_test_tool", async () => {
      throw new ValidationError("Invalid input", []);
    });

    const result = await handler({});
    expect(result.isError).toBe(true);
    const errorPayload = result.structuredContent?.["error"] as Record<string, unknown>;
    const contextIds = errorPayload["contextIds"] as Record<string, unknown>;
    expect(typeof contextIds["traceId"]).toBe("string");
    expect(typeof contextIds["requestId"]).toBe("string");
    expect(String(contextIds["traceId"])).toMatch(UUID_PATTERN);
    expect(String(contextIds["requestId"])).toMatch(UUID_PATTERN);
    expect(errorPayload["category"]).toBe("client_input");
    expect(errorPayload["severity"]).toBe("low");
    expect((result.content[0] as { text: string }).text).toContain("Trace ID:");
  });

  it("preserves explicitly supplied contextIds in payload conversion", () => {
    const contextIds = {
      traceId: "11111111-1111-4111-8111-111111111111",
      requestId: "22222222-2222-4222-8222-222222222222",
    } as const;
    const payload = toToolErrorPayload(
      new ApiError({
        apiName: "test-api",
        source: "test-source",
        statusCode: 503,
        code: "RETRY_EXHAUSTED",
        retryable: true,
        message: "Upstream unavailable",
      }),
      "sg_test_tool",
      { contextIds },
    );
    expect(payload.contextIds).toEqual(contextIds);
    expect(payload.category).toBe("upstream_reliability");
    expect(payload.severity).toBe("high");
  });

  it("applies HTTP code taxonomy fallback when the upstream error code is HTTP_*", () => {
    const payload = toToolErrorPayload(
      new ApiError({
        apiName: "test-api",
        source: "test-source",
        statusCode: 429,
        code: "HTTP_429",
        retryable: true,
        message: "Too many requests",
      }),
      "sg_test_tool",
    );
    expect(payload.category).toBe("upstream_reliability");
    expect(payload.severity).toBe("medium");
    expect(payload.suggestedAction).toBe("Respect retry-after guidance or reduce request rate before retrying.");
  });

  it("adds contextIds to successful results when SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS=1", async () => {
    const previous = process.env["SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS"];
    process.env["SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS"] = "1";
    try {
      const handler = wrapHandler("sg_test_tool", async () => ({
        content: [{ type: "text", text: "ok" }],
      }));

      const result = await handler({});
      const contextIds = result.structuredContent?.["contextIds"] as Record<string, unknown>;
      expect(typeof contextIds["traceId"]).toBe("string");
      expect(typeof contextIds["requestId"]).toBe("string");
      expect(String(contextIds["traceId"])).toMatch(UUID_PATTERN);
      expect(String(contextIds["requestId"])).toMatch(UUID_PATTERN);
    } finally {
      if (previous === undefined) {
        delete process.env["SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS"];
      } else {
        process.env["SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS"] = previous;
      }
    }
  });

  it("does not overwrite existing success contextIds", async () => {
    const previous = process.env["SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS"];
    process.env["SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS"] = "1";
    try {
      const existingContextIds = {
        traceId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        requestId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      };
      const handler = wrapHandler("sg_test_tool", async () => ({
        content: [{ type: "text", text: "ok" }],
        structuredContent: {
          contextIds: existingContextIds,
        },
      }));

      const result = await handler({});
      expect(result.structuredContent?.["contextIds"]).toEqual(existingContextIds);
    } finally {
      if (previous === undefined) {
        delete process.env["SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS"];
      } else {
        process.env["SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS"] = previous;
      }
    }
  });
});
