import { describe, expect, it } from "vitest";

import { ProviderRequestError } from "../../ai/providers.js";
import type { AnalystMemoDossier } from "../analyst-memo.js";
import { generateInteractiveSummary } from "../interactive-summary.js";

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
        title: "Sanctions Screen",
      },
      {
        freshness: [{ observedAt: "2026-05-15T00:00:00.000Z", source: "OpenCorporates" }],
        gaps: [{ code: "OPENCORPORATES_API_TOKEN_REQUIRED", message: "OpenCorporates credentials are not configured." }],
        limits: [{ code: "SUPPLEMENTAL_REVIEW", message: "OpenCorporates links require analyst review." }],
        provenance: [{ authRequired: true, coverage: "OpenCorporates candidate links.", recordCount: 0, source: "OpenCorporates", tool: "sg_opencorporates_links" }],
        records: [],
        riskFlags: [],
        summary: [{ label: "OpenCorporates provider", value: "credential gap" }],
        title: "OpenCorporates Cross-Links",
      },
      {
        freshness: [{ observedAt: "2026-05-15T00:00:00.000Z", source: "Official feeds" }],
        gaps: [],
        limits: [{ code: "OFFICIAL_FEEDS_ONLY", message: "Adverse media lite searches bounded official feeds only." }],
        provenance: [{ authRequired: false, coverage: "Official-feed keyword search.", recordCount: 0, source: "Official feeds", tool: "sg_adverse_media_lite" }],
        records: [],
        riskFlags: [],
        summary: [{ label: "Feed items matched", value: 0 }],
        title: "Adverse Media Lite",
      },
      {
        freshness: [{ observedAt: "2026-05-15T00:00:00.000Z", source: "Dude relationship graph" }],
        gaps: [],
        limits: [{ code: "RELATIONSHIP_GRAPH_LIMITED", message: "Graph is built only from returned dossier records." }],
        provenance: [{ authRequired: false, coverage: "Relationship graph from retained module records.", recordCount: 1, source: "Dude relationship graph", tool: "sg_relationship_graph" }],
        records: [{ nodes: [{ id: "entity:03591300B", label: "DBS BANK LTD" }], edges: [] }],
        riskFlags: [],
        summary: [{ label: "Relationship graph nodes", value: 1 }],
        title: "Relationship Graph",
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

describe("interactive summary generation", () => {
  it("returns unavailable when provider credentials are missing", async () => {
    const summary = await generateInteractiveSummary(
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
          limits: ["Web discovery is supplemental."],
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
        },
      },
      {
        env: {
          VITE_OPENAI_API_KEY: "browser-secret",
        } as NodeJS.ProcessEnv,
        generatedAt: new Date("2026-05-15T00:00:00.000Z"),
      },
    );

    expect(summary).toMatchObject({
      configured: false,
      generatedAt: "2026-05-15T00:00:00.000Z",
      prompt: {
        copyText: expect.stringContaining("SYSTEM\nYou write one-sentence interactive summaries"),
      },
      provider: "openai",
      reason: {
        code: "AI_PROVIDER_UNCONFIGURED",
      },
      status: "unavailable",
    });
  });

  it("grounds one-sentence model segments to known UI targets", async () => {
    const summary = await generateInteractiveSummary(
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
          limits: ["Web discovery is supplemental."],
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
        },
      },
      {
        env: {
          DUDE_AI_PROVIDER: "openai",
          OPENAI_API_KEY: "server-key",
        } as NodeJS.ProcessEnv,
        generate: async (input, config) => {
          expect(input.prompt).toContain("overview.summary");
          expect(input.prompt).toContain("evidence.records");
          expect(input.prompt).toContain("compositeEvidencePacks");
          expect(input.prompt).toContain("externalDiligence");
          expect(input.prompt).toContain("Sanctions Screen");
          expect(input.prompt).toContain("OpenCorporates Cross-Links");
          expect(input.prompt).toContain("Adverse Media Lite");
          expect(input.prompt).toContain("Relationship Graph");
          expect(input.prompt).toContain("supplementalReview");
          expect(input.prompt).toContain("DBS official website result");
          expect(input.prompt).toContain("Snippet mentioning DBS leadership context");
          return {
            model: config.model,
            provider: config.provider,
            text: JSON.stringify({
              segments: [
                { emphasized: false, targetId: "overview.summary", text: "The dossier identifies " },
                { emphasized: true, targetId: "overview.summary", text: "DBS BANK LTD" },
                { emphasized: false, targetId: "evidence.records", text: " with " },
                { emphasized: true, targetId: "evidence.records", text: "ACRA evidence" },
                { emphasized: false, targetId: "overview.risk", text: " and " },
                { emphasized: true, targetId: "overview.risk", text: "one partial-coverage risk signal" },
                { emphasized: false, targetId: "audit.gaps", text: "." },
              ],
            }),
          };
        },
        generatedAt: new Date("2026-05-15T00:00:00.000Z"),
      },
    );

    expect(summary.status).toBe("ready");
    if (summary.status !== "ready") return;
    expect(summary.sentence).toBe("The dossier identifies DBS BANK LTD with ACRA evidence and one partial-coverage risk signal.");
    expect(summary.prompt.copyText).toContain("USER\n");
    expect(summary.prompt.copyText).toContain("\"targetIds\"");
    expect(summary.segments.filter((segment) => segment.emphasized)).toEqual([
      expect.objectContaining({ targetId: "overview.summary", text: "DBS BANK LTD" }),
      expect.objectContaining({ targetId: "evidence.records", text: "ACRA evidence" }),
      expect.objectContaining({ targetId: "overview.risk", text: "one partial-coverage risk signal" }),
    ]);
  });

  it("routes missing-section links to provenance when no gaps exist", async () => {
    const summary = await generateInteractiveSummary(
      { dossier: { ...fixtureDossier, gaps: [] } },
      {
        env: {
          DUDE_AI_PROVIDER: "openai",
          OPENAI_API_KEY: "server-key",
        } as NodeJS.ProcessEnv,
        generate: async (input, config) => {
          expect(input.prompt).toContain("Use audit.gaps only when dossier.gaps is non-empty");
          return {
            model: config.model,
            provider: config.provider,
            text: JSON.stringify({
              segments: [
                { emphasized: false, targetId: "overview.summary", text: "The dossier identifies " },
                { emphasized: true, targetId: "overview.summary", text: "DBS BANK LTD" },
                { emphasized: false, targetId: "audit.gaps", text: " with " },
                { emphasized: true, targetId: "audit.gaps", text: "bounded public-data coverage" },
                { emphasized: false, targetId: "audit.gaps", text: "." },
              ],
            }),
          };
        },
        generatedAt: new Date("2026-05-15T00:00:00.000Z"),
      },
    );

    expect(summary.status).toBe("ready");
    if (summary.status !== "ready") return;
    expect(summary.segments.filter((segment) => segment.targetId === "audit.gaps")).toEqual([]);
    expect(summary.segments.filter((segment) => segment.emphasized)).toContainEqual(
      expect.objectContaining({ targetId: "audit.provenance", text: "bounded public-data coverage" }),
    );
  });

  it("returns unavailable instead of failing hard when provider credentials are rejected", async () => {
    const summary = await generateInteractiveSummary(
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

    expect(summary).toMatchObject({
      configured: false,
      provider: "openai",
      reason: {
        code: "AI_PROVIDER_AUTH_FAILED",
        message: expect.stringContaining("OPENAI_API_KEY"),
      },
      status: "unavailable",
    });
  });
});
