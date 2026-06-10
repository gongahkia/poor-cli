import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { GatewayStatusPanel, getGatewayReadinessIssues } from "@/components/status/GatewayStatus";
import type { GatewayHealth } from "@/lib/api/client";

const baseHealth: GatewayHealth = {
  readiness: "ready",
  services: {
    acraLookup: {
      message: "ACRA lookup path returned rows.",
      status: "ready",
    },
    datagovDatastore: {
      message: "data.gov.sg datastore returned rows.",
      status: "ready",
    },
    gateway: {
      message: "HTTP gateway is reachable.",
      status: "ready",
    },
    tinyfish: {
      configured: true,
      message: "Optional web-evidence provider accepted the readiness query.",
      mode: "web-discovery-only",
      status: "ready",
    },
    splunkMcp: {
      configured: true,
      details: {
        allowedIndexesConfigured: true,
        probeMode: "config_only",
        tokenConfigured: true,
        tokenSource: "env",
        urlConfigured: true,
      },
      message: "Splunk MCP proxy is configured. Live upstream authentication was not probed.",
      status: "ready",
    },
  },
  status: "ok",
  tools: 105,
};

describe("getGatewayReadinessIssues", () => {
  it("flags explain-only AI provider failures without dossier language", () => {
    const issues = getGatewayReadinessIssues({
      ...baseHealth,
      readiness: "degraded",
      services: {
        ...baseHealth.services,
        analystMemo: {
          configured: true,
          errorCode: "AI_PROVIDER_AUTH_FAILED",
          message:
            "openai credentials were rejected by the provider. Check OPENAI_API_KEY on the REST gateway process.",
          model: "gpt-4o",
          provider: "openai",
          status: "failing",
        },
      },
      status: "degraded",
    });

    expect(issues).toEqual([
      expect.objectContaining({
        key: "analystMemo",
        label: "OpenAI explain key",
        state: "Failing",
        tone: "bad",
      }),
    ]);
    expect(issues[0]?.detail).toContain("OPENAI_API_KEY");
    expect(issues[0]?.detail).toContain("AI_PROVIDER_AUTH_FAILED");
  });

  it("keeps the landing page quiet when all visible services are ready", () => {
    expect(getGatewayReadinessIssues(baseHealth)).toEqual([]);
  });

  it("flags Splunk MCP setup without requiring a live token", () => {
    const issues = getGatewayReadinessIssues({
      ...baseHealth,
      services: {
        ...baseHealth.services,
        splunkMcp: {
          configured: false,
          details: {
            allowedIndexesConfigured: false,
            probeMode: "config_only",
            tokenConfigured: false,
            tokenSource: "none",
            urlConfigured: false,
          },
          message:
            "Set SPLUNK_MCP_URL and SPLUNK_MCP_TOKEN or a splunk_mcp keystore entry to enable Splunk proxy tools.",
          status: "unconfigured",
        },
      },
    });

    expect(issues).toEqual([
      expect.objectContaining({
        key: "splunkMcp",
        label: "Splunk MCP proxy",
        state: "Unconfigured",
        tone: "warn",
      }),
    ]);
    expect(issues[0]?.detail).toContain("SPLUNK_MCP_URL");
    expect(issues[0]?.detail).toContain("splunk_mcp");
  });

  it("keeps the explain-only AI readiness metadata compact", () => {
    const html = renderToStaticMarkup(
      createElement(
        GatewayStatusPanel,
        {
          health: {
            ...baseHealth,
            services: {
              ...baseHealth.services,
              analystMemo: {
                configured: true,
                details: {
                  credentialLocation: "REST gateway process environment",
                  model: "gpt-4o",
                  provider: "openai",
                  requiredEnvVar: "OPENAI_API_KEY",
                },
                latencyMs: 943,
                message: "Explain-only AI provider accepted the readiness probe.",
                model: "gpt-4o",
                provider: "openai",
                status: "ready",
              },
            },
          },
        },
      ),
    );

    expect(html).toContain("OpenAI explain key");
    expect(html).toContain("Probe");
    expect(html).toContain("943ms");
    expect(html).toContain("Provider");
    expect(html).toContain("OpenAI");
    expect(html).toContain("Model");
    expect(html).toContain("gpt-4o");
    expect(html).not.toContain("Required env");
    expect(html).not.toContain("OPENAI_API_KEY");
    expect(html).not.toContain("Stored in");
    expect(html).not.toContain("REST gateway process environment");
    expect(html).not.toContain("Browser env");
    expect(html).not.toContain("browser VITE_* keys are not used");
  });

  it("renders Splunk MCP readiness as config-only metadata", () => {
    const html = renderToStaticMarkup(
      createElement(GatewayStatusPanel, {
        health: baseHealth,
      }),
    );

    expect(html).toContain("Splunk MCP proxy");
    expect(html).toContain("config-only");
    expect(html).toContain("Token");
    expect(html).toContain("env");
    expect(html).toContain("URL");
    expect(html).toContain("configured");
    expect(html).not.toContain("authenticated");
  });
});
