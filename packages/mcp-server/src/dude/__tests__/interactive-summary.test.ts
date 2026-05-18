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
      { dossier: fixtureDossier },
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
      { dossier: fixtureDossier },
      {
        env: {
          DUDE_AI_PROVIDER: "openai",
          OPENAI_API_KEY: "server-key",
        } as NodeJS.ProcessEnv,
        generate: async (input, config) => {
          expect(input.prompt).toContain("overview.summary");
          expect(input.prompt).toContain("evidence.records");
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
