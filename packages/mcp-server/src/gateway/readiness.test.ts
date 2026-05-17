import { describe, expect, it, vi } from "vitest";

vi.mock("../apis/acra/client.js", () => ({
  probeAcraLookupReadiness: vi.fn(async () => ({
    fieldCount: 8,
    recordCount: 1,
    resourceId: "acra-resource",
  })),
}));

vi.mock("../apis/tinyfish/client.js", () => ({
  probeTinyFishSearchReadiness: vi.fn(async () => ({
    configured: true,
    resultCount: 1,
  })),
}));

vi.mock("../tools/health-check.js", () => ({
  probeDatagovDatastoreHealth: vi.fn(async () => undefined),
}));

vi.mock("../ai/providers.js", () => {
  class ProviderRequestError extends Error {
    readonly provider: "anthropic" | "google" | "openai";
    readonly status: number;

    constructor(provider: "anthropic" | "google" | "openai", status: number) {
      super(`${provider} request failed: ${status}`);
      this.name = "ProviderRequestError";
      this.provider = provider;
      this.status = status;
    }
  }

  return {
    ProviderRequestError,
    generateText: vi.fn(),
    resolveAiProviderConfig: vi.fn(() => ({
      apiKey: "stale-key",
      configured: true,
      model: "gpt-4o",
      provider: "openai",
    })),
  };
});

const { generateText, ProviderRequestError } = await import("../ai/providers.js");
const { getGatewayHealthPayload } = await import("./readiness.js");

describe("gateway readiness", () => {
  it("surfaces analyst memo provider auth failures before dossier generation", async () => {
    vi.mocked(generateText).mockRejectedValueOnce(new ProviderRequestError("openai", 401));

    const health = await getGatewayHealthPayload({
      startedAt: new Date("2026-05-17T00:00:00.000Z"),
      toolCount: 105,
    });

    expect(health.status).toBe("ok");
    expect(health.readiness).toBe("degraded");
    expect(health.services.analystMemo).toMatchObject({
      configured: true,
      errorCode: "AI_PROVIDER_AUTH_FAILED",
      model: "gpt-4o",
      provider: "openai",
      retryable: false,
      status: "failing",
    });
    expect(health.services.analystMemo.message).toContain("OPENAI_API_KEY");
  });
});
