import { describe, expect, it } from "vitest";

import { generateAnalystMemo, type AnalystMemoDossier } from "../analyst-memo.js";

const fixtureDossier: AnalystMemoDossier = {
  evidence: [
    { label: "Matched modules", source: "Resolver", value: 1 },
  ],
  freshness: [
    { observedAt: "2026-05-15T00:00:00.000Z", source: "ACRA", upstreamTimestamp: "2026-05-14" },
  ],
  gaps: [
    { code: "GEBIZ_NO_MATCH", message: "No GeBIZ awards returned." },
  ],
  limits: [
    { code: "PUBLIC_DATA_ONLY", message: "Public registries do not expose ownership graphs here." },
  ],
  provenance: [
    {
      authRequired: false,
      coverage: "Exact-match company and UEN registry evidence.",
      recordCount: 1,
      source: "ACRA",
      tool: "sg_acra_entities",
    },
  ],
  records: {
    quality: { confidence: "high" },
    resolution: { matchedModules: ["acra"], searchedModules: ["acra", "gebiz"] },
  },
  riskFlags: [
    { code: "PARTIAL_MODULE_COVERAGE", message: "One searched module did not match.", severity: "medium", source: "Resolver" },
  ],
  summary: [
    { label: "Entity", source: "ACRA", value: "DBS BANK LTD" },
    { label: "UEN", source: "ACRA", value: "03591300B" },
  ],
  title: "Business Dossier",
};

describe("analyst memo generation", () => {
  it("returns a structured unavailable state when provider credentials are missing", async () => {
    const memo = await generateAnalystMemo(
      { dossier: fixtureDossier },
      {
        env: {
          VITE_OPENAI_API_KEY: "browser-secret",
        } as NodeJS.ProcessEnv,
        generatedAt: new Date("2026-05-15T00:00:00.000Z"),
      },
    );

    expect(memo).toMatchObject({
      configured: false,
      generatedAt: "2026-05-15T00:00:00.000Z",
      provider: "openai",
      reason: {
        code: "AI_PROVIDER_UNCONFIGURED",
      },
      status: "unavailable",
    });
  });

  it("keeps only model claims that cite dossier evidence", async () => {
    const memo = await generateAnalystMemo(
      {
        dossier: fixtureDossier,
        webPresence: {
          configured: true,
          limits: ["Web discovery is supplemental."],
        },
      },
      {
        env: {
          DUDE_AI_PROVIDER: "openai",
          OPENAI_API_KEY: "server-key",
        } as NodeJS.ProcessEnv,
        generate: async (input, config) => {
          expect(input.prompt).toContain("webPresenceLimits");
          expect(input.prompt).toContain("Web discovery is supplemental.");
          return {
            model: config.model,
            provider: config.provider,
            text: JSON.stringify({
              decisionAid: {
                confidenceBlockers: ["GeBIZ had no fixture match."],
                nextSteps: ["Run direct GeBIZ follow-up only if procurement history matters operationally."],
              },
              evidenceMemo: [
                { citationIds: ["summary-1"], text: "The entity name is present in the ACRA summary." },
                { citationIds: [], text: "The company has undisclosed shareholders." },
              ],
              limits: ["No ownership graph is present in the dossier."],
              riskRating: {
                citationIds: ["risk-1"],
                confidenceBlockers: ["Procurement evidence is incomplete."],
                level: "medium",
                rationale: "Partial module coverage is the main risk signal.",
              },
            }),
          };
        },
        generatedAt: new Date("2026-05-15T00:00:00.000Z"),
      },
    );

    expect(memo.status).toBe("ready");
    if (memo.status !== "ready") return;
    expect(memo.evidenceMemo).toHaveLength(1);
    expect(memo.evidenceMemo[0]).toMatchObject({
      citationIds: ["summary-1"],
    });
    expect(memo.rejectedClaims).toEqual([
      {
        claim: "The company has undisclosed shareholders.",
        reason: "No valid dossier citation id was supplied.",
      },
    ]);
    expect(memo.riskRating).toMatchObject({
      level: "medium",
    });
    expect(memo.decisionAid.nonAdvisoryReminder).toContain("Operational follow-up only");
  });
});
