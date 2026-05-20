import { afterEach, describe, expect, it, vi } from "vitest";

import { callTool, getGatewayJson, postGatewayJson } from "@/lib/api/client";

describe("api client errors", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("surfaces nested gateway error messages for tool calls", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
      JSON.stringify({ error: { message: "Nested failure" } }),
      { status: 429 },
    ));

    await expect(callTool("sg_business_dossier", {})).rejects.toThrow("Nested failure");
  });

  it("surfaces nested gateway error messages for GET and POST helper calls", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(
      JSON.stringify({ error: { message: "Gateway unavailable" } }),
      { status: 503 },
    ));

    await expect(getGatewayJson("/api/v1/health")).rejects.toThrow("Gateway unavailable");
    await expect(postGatewayJson("/api/v1/dude/memo", {})).rejects.toThrow("Gateway unavailable");
  });

  it("adds setup context for network and CORS fetch failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(getGatewayJson("/api/v1/health")).rejects.toThrow("DUDE_WEB_ORIGIN_ALLOWLIST");
    await expect(getGatewayJson("/api/v1/health")).rejects.toThrow("Failed to fetch");
  });
});
