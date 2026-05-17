import { describe, expect, it } from "vitest";

import { getGatewayReadinessIssues } from "@/components/status/GatewayStatus";
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
      message: "TinyFish search accepted the readiness query.",
      mode: "web-discovery-only",
      status: "ready",
    },
  },
  status: "ok",
  tools: 105,
};

describe("getGatewayReadinessIssues", () => {
  it("flags analyst memo provider failures before a dossier is generated", () => {
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
        label: "Analyst memo",
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
});
