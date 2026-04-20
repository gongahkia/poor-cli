import { ApiError, ValidationError } from "@sg-apis/shared";
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
        code: "UPSTREAM_DOWN",
        retryable: true,
        message: "Upstream unavailable",
      }),
      "sg_test_tool",
      { contextIds },
    );
    expect(payload.contextIds).toEqual(contextIds);
  });
});
