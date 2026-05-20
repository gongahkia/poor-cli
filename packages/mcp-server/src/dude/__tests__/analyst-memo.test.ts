import { describe, expect, it } from "vitest";

import { ProviderRequestError } from "../../ai/providers.js";
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
    acra: [
      {
        entityName: "DBS BANK LTD",
        entityStatusDescription: "Live Company",
        uen: "03591300B",
      },
    ],
    externalDiligence: [
      {
        freshness: [{ observedAt: "2026-05-15T00:00:00.000Z", source: "OpenSanctions" }],
        gaps: [{ code: "OPENSANCTIONS_API_KEY_REQUIRED", message: "OpenSanctions credentials are not configured." }],
        limits: [{ code: "SUPPLEMENTAL_REVIEW", message: "Sanctions results require analyst review." }],
        provenance: [{ authRequired: true, coverage: "Sanctions candidate screening.", recordCount: 0, source: "OpenSanctions", tool: "sg_sanctions_screen" }],
        records: [],
        riskFlags: [],
        summary: [{ label: "Sanctions provider", value: "credential gap" }],
        title: "Sanctions screen",
      },
      {
        freshness: [{ observedAt: "2026-05-15T00:00:00.000Z", source: "OpenCorporates" }],
        gaps: [{ code: "OPENCORPORATES_API_TOKEN_REQUIRED", message: "OpenCorporates credentials are not configured." }],
        limits: [{ code: "SUPPLEMENTAL_REVIEW", message: "OpenCorporates links require analyst review." }],
        provenance: [{ authRequired: true, coverage: "OpenCorporates candidate links.", recordCount: 0, source: "OpenCorporates", tool: "sg_opencorporates_links" }],
        records: [],
        riskFlags: [],
        summary: [{ label: "OpenCorporates provider", value: "credential gap" }],
        title: "OpenCorporates links",
      },
      {
        freshness: [{ observedAt: "2026-05-15T00:00:00.000Z", source: "Official feeds" }],
        gaps: [],
        limits: [{ code: "OFFICIAL_FEEDS_ONLY", message: "Adverse media lite searches bounded official feeds only." }],
        provenance: [{ authRequired: false, coverage: "Official-feed keyword search.", recordCount: 0, source: "Official feeds", tool: "sg_adverse_media_lite" }],
        records: [],
        riskFlags: [],
        summary: [{ label: "Feed items matched", value: 0 }],
        title: "Adverse media lite",
      },
      {
        freshness: [{ observedAt: "2026-05-15T00:00:00.000Z", source: "Dude relationship graph" }],
        gaps: [],
        limits: [{ code: "RELATIONSHIP_GRAPH_LIMITED", message: "Graph is built only from returned dossier records." }],
        provenance: [{ authRequired: false, coverage: "Relationship graph from retained module records.", recordCount: 1, source: "Dude relationship graph", tool: "sg_relationship_graph" }],
        records: [{ nodes: [{ id: "entity:03591300B", label: "DBS BANK LTD" }], edges: [] }],
        riskFlags: [],
        summary: [{ label: "Relationship graph nodes", value: 1 }],
        title: "Relationship graph",
      },
    ],
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

  it("returns memo unavailable instead of a hard error when provider credentials are rejected", async () => {
    const memo = await generateAnalystMemo(
      { dossier: fixtureDossier },
      {
        env: {
          DUDE_AI_PROVIDER: "openai",
          OPENAI_API_KEY: "stale-server-key",
        } as NodeJS.ProcessEnv,
        generate: async () => {
          throw new ProviderRequestError("openai", 401);
        },
        generatedAt: new Date("2026-05-15T00:00:00.000Z"),
      },
    );

    expect(memo).toMatchObject({
      configured: false,
      generatedAt: "2026-05-15T00:00:00.000Z",
      provider: "openai",
      reason: {
        code: "AI_PROVIDER_AUTH_FAILED",
        message: expect.stringContaining("OPENAI_API_KEY"),
      },
      status: "unavailable",
    });
  });

  it("keeps only model claims that cite dossier evidence", async () => {
    const memo = await generateAnalystMemo(
      {
        dossier: fixtureDossier,
        peopleDiscovery: {
          configured: true,
          entityName: "DBS BANK LTD",
          limits: ["People discovery is supplemental analyst-review evidence."],
          query: "DBS BANK LTD leadership Singapore",
          results: [
            {
              position: 1,
              siteName: "example.com",
              snippet: "Snippet mentioning DBS leadership context.",
              title: "DBS leadership result",
              url: "https://example.com/dbs-leadership",
            },
          ],
          suggestedActions: ["Verify named persons against official filings before relying on authority."],
          uen: "03591300B",
        },
        webPresence: {
          configured: true,
          possibleOfficialWebsite: "https://www.dbs.com",
          query: "DBS BANK LTD 03591300B",
          results: [
            {
              position: 1,
              siteName: "dbs.com",
              snippet: "DBS official website result.",
              title: "DBS official site",
              url: "https://www.dbs.com",
            },
          ],
          limits: ["Web discovery is supplemental."],
        },
      },
      {
        env: {
          DUDE_AI_PROVIDER: "openai",
          OPENAI_API_KEY: "server-key",
        } as NodeJS.ProcessEnv,
        generate: async (input, config) => {
          expect(input.prompt).toContain("supplementalReview");
          expect(input.prompt).toContain("web-presence-1");
          expect(input.prompt).toContain("people-discovery-1");
          expect(input.prompt).toContain("record-acra-1");
          expect(input.prompt).toContain("externalDiligence");
          expect(input.prompt).toContain("Sanctions screen");
          expect(input.prompt).toContain("OpenCorporates links");
          expect(input.prompt).toContain("Adverse media lite");
          expect(input.prompt).toContain("Relationship graph");
          expect(input.prompt).toContain("Web discovery is supplemental.");
          expect(input.prompt).toContain("People discovery is supplemental analyst-review evidence.");
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
                { citationIds: ["web-presence-1"], text: "A supplemental web-presence result is available for analyst review." },
                { citationIds: ["people-discovery-1"], text: "A people-discovery snippet is available for analyst review." },
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
    expect(memo.evidenceMemo).toHaveLength(3);
    expect(memo.evidenceMemo[0]).toMatchObject({
      citationIds: ["summary-1"],
    });
    expect(memo.evidenceMemo[1]).toMatchObject({
      citationIds: ["web-presence-1"],
    });
    expect(memo.evidenceMemo[2]).toMatchObject({
      citationIds: ["people-discovery-1"],
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
