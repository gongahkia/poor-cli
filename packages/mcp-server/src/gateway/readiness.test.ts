import { afterEach, describe, expect, it, vi } from "vitest";

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

vi.mock("../upstreams/splunk/mcp-client.js", () => ({
  inspectSplunkMcpConfig: vi.fn(() => ({
    allowedIndexesConfigured: false,
    configured: false,
    tokenConfigured: false,
    tokenSource: "none",
    urlConfigured: false,
  })),
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
const { inspectSplunkMcpConfig } = await import("../upstreams/splunk/mcp-client.js");
const { getGatewayHealthPayload, resetGatewayReadinessCacheForTesting } = await import("./readiness.js");

describe("gateway readiness", () => {
  afterEach(() => {
    resetGatewayReadinessCacheForTesting();
    vi.clearAllMocks();
  });

  it("surfaces explain-only AI provider auth failures", async () => {
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

  it("surfaces Splunk MCP as config-only readiness without probing upstream", async () => {
    vi.mocked(inspectSplunkMcpConfig).mockReturnValueOnce({
      allowedIndexesConfigured: true,
      configured: true,
      tokenConfigured: true,
      tokenSource: "env",
      urlConfigured: true,
    });

    const health = await getGatewayHealthPayload({
      startedAt: new Date("2026-05-17T00:00:00.000Z"),
      toolCount: 108,
    });

    expect(health.services.splunkMcp).toMatchObject({
      configured: true,
      status: "ready",
      details: {
        allowedIndexesConfigured: true,
        probeMode: "config_only",
        tokenSource: "env",
      },
    });
  });

  it("leaves Splunk MCP unconfigured without changing required readiness", async () => {
    const health = await getGatewayHealthPayload({
      startedAt: new Date("2026-05-17T00:00:00.000Z"),
      toolCount: 108,
    });

    expect(health.services.splunkMcp).toMatchObject({
      configured: false,
      status: "unconfigured",
      details: {
        tokenSource: "none",
        urlConfigured: false,
      },
    });
    expect(health.status).toBe("ok");
  });

  it("marks gateway readiness failing when production auth is fail-closed", async () => {
    const health = await getGatewayHealthPayload({
      gateway: {
        status: "failing",
        message: "Production REST gateway is fail-closed because no auth config is present.",
        observedAt: "2026-05-18T00:00:00.000Z",
        details: {
          authRequired: true,
          production: true,
          productionFailClosed: true,
        },
      },
      startedAt: new Date("2026-05-17T00:00:00.000Z"),
      toolCount: 105,
    });

    expect(health.status).toBe("degraded");
    expect(health.readiness).toBe("failing");
    expect(health.services.gateway).toMatchObject({
      status: "failing",
      details: {
        authRequired: true,
        productionFailClosed: true,
      },
    });
  });
});
