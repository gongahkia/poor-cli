import { describe, expect, it } from "vitest";

import {
  buildAdverseMediaLiteArtifact,
  buildOpenCorporatesLinksArtifact,
  buildRelationshipGraphArtifact,
  buildSanctionsScreenArtifact,
} from "../external-diligence.js";

describe("OpenSanctions screening", () => {
  it("classifies exact, fuzzy, and no-match candidate outcomes", async () => {
    const exact = await buildSanctionsScreenArtifact(
      { name: "ACME PTE LTD", threshold: 0.75 },
      {
        apiKey: "test",
        observedAt: "2026-05-17T00:00:00.000Z",
        fetcher: async () => ({
          ok: true,
          status: 200,
          json: async () => ({
            responses: {
              q0: {
                results: [{ id: "os-1", caption: "ACME PTE LTD", score: 0.99 }],
              },
            },
          }),
        }),
      },
    );
    expect(exact.summary).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Match type", value: "exact" }),
    ]));
    expect(exact.riskFlags?.[0]).toMatchObject({ code: "SANCTIONS_EXACT_CANDIDATE" });

    const fuzzy = await buildSanctionsScreenArtifact(
      { name: "ACME PTE LTD", threshold: 0.75 },
      {
        apiKey: "test",
        fetcher: async () => ({
          ok: true,
          status: 200,
          json: async () => ({ results: [{ id: "os-2", caption: "ACME HOLDINGS", score: 0.86 }] }),
        }),
      },
    );
    expect(fuzzy.summary).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Match type", value: "fuzzy" }),
    ]));

    const none = await buildSanctionsScreenArtifact(
      { name: "ACME PTE LTD", threshold: 0.75 },
      {
        apiKey: "test",
        fetcher: async () => ({
          ok: true,
          status: 200,
          json: async () => ({ results: [{ id: "os-3", caption: "OTHER", score: 0.2 }] }),
        }),
      },
    );
    expect(none.summary).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Match type", value: "no-match" }),
    ]));
  });

  it("returns a bounded upstream gap instead of throwing", async () => {
    const artifact = await buildSanctionsScreenArtifact(
      { name: "ACME PTE LTD" },
      {
        apiKey: "test",
        fetcher: async () => ({ ok: false, status: 503, json: async () => ({}) }),
      },
    );
    expect(artifact.gaps).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "OPENSANCTIONS_UPSTREAM_FAILED" }),
    ]));
  });
});

describe("OpenCorporates links", () => {
  it("marks ambiguous and no-match outcomes without ownership claims", async () => {
    const artifact = await buildOpenCorporatesLinksArtifact(
      { entityName: "ACME PTE LTD", uen: "202400001A" },
      {
        apiToken: "test",
        fetcher: async () => ({
          ok: true,
          status: 200,
          json: async () => ({
            results: {
              companies: [
                { company: { name: "ACME PTE LTD", company_number: "202400001A" } },
                { company: { name: "ACME HOLDINGS", company_number: "202400002B" } },
              ],
            },
          }),
        }),
      },
    );

    expect(artifact.evidence).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Ambiguous candidates", value: 1 }),
    ]));
    expect(artifact.limits.map((limit) => limit.code)).toContain("NO_OWNERSHIP_CLAIMS");

    const none = await buildOpenCorporatesLinksArtifact(
      { entityName: "ACME PTE LTD" },
      {
        apiToken: "test",
        fetcher: async () => ({ ok: true, status: 200, json: async () => ({ results: { companies: [] } }) }),
      },
    );
    expect(none.gaps).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "OPENCORPORATES_NO_MATCH" }),
    ]));
  });
});

describe("adverse media lite", () => {
  it("searches bounded official feeds and declares no unsupported NLP", async () => {
    const artifact = await buildAdverseMediaLiteArtifact(
      { keyword: "ACME", feedIds: ["sfa_food_alerts"], limitPerFeed: 5 },
      {
        feedReader: async () => ({
          feed: {
            id: "sfa_food_alerts",
            title: "SFA Food Alerts",
            family: "sfa",
            sourceAgency: "Singapore Food Agency",
            sourceUrl: "https://www.sfa.gov.sg/rss/annual-listing-food-alerts",
          },
          observedAt: "2026-05-17T00:00:00.000Z",
          cached: false,
          channelTitle: "SFA Food Alerts",
          records: [{
            title: "ACME product recall",
            description: "Official notice",
            link: "https://example.test/acme",
            guid: "1",
            publishedAtRaw: "17 May 2026",
            publishedAt: "2026-05-17T00:00:00.000Z",
          }],
        }),
      },
    );

    expect(artifact.records.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        confidence: "official_feed_keyword_match",
        triage: expect.objectContaining({
          adverseEventCategory: "not_assessed",
          culpability: "not_assessed",
          matchedFeed: "sfa_food_alerts",
          matchedKeywords: expect.arrayContaining(["acme"]),
          officialNoticeType: "official_food_alert_feed",
          requiresAnalystReview: true,
          sentiment: "not_assessed",
        }),
      }),
    ]));
    expect(artifact.evidence).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Triage model", value: "feed_metadata_and_keyword_match_only" }),
      expect.objectContaining({ label: "Unsupported assessments", value: "sentiment, culpability, adverse_event_category" }),
    ]));
    expect(artifact.limits.map((limit) => limit.code)).toContain("NO_UNSUPPORTED_NLP");
  });
});

describe("relationship graph", () => {
  it("creates shared-address and sibling heuristic edges with strict limitations", () => {
    const artifact = buildRelationshipGraphArtifact({
      records: {
        acra: [
          { entityName: "ACME HOLDINGS PTE LTD", uen: "202400001A", streetName: "Anson Road", postalCode: "079903" },
          { entityName: "ACME HOLDINGS PRIVATE LIMITED", uen: "202400002B", streetName: "Anson Road", postalCode: "079903" },
        ],
      },
    }, "2026-05-17T00:00:00.000Z");

    const graph = artifact.records.graph as { edges: { kind: string }[] };
    expect(graph.edges.map((edge) => edge.kind)).toEqual(expect.arrayContaining([
      "shared_registered_address",
      "name_family",
    ]));
    expect(artifact.limits.map((limit) => limit.code)).toContain("NO_INFERRED_OWNERSHIP_OR_CONTROL");
  });

  it("represents explicit source-declared relationships without inferring control", () => {
    const artifact = buildRelationshipGraphArtifact({
      records: {
        acra: [
          { entityName: "ACME HOLDINGS PTE LTD", uen: "202400001A" },
        ],
        relationships: [
          {
            from: "ACME HOLDINGS PTE LTD",
            to: "ACME OPERATING PTE LTD",
            relationshipType: "declared_parent",
            source: "Supplied registry extract",
            evidence: "Registry extract states ACME HOLDINGS PTE LTD is the parent entity.",
          },
        ],
      },
    }, "2026-05-17T00:00:00.000Z");

    const graph = artifact.records.graph as { edges: { confidence: string; kind: string }[] };
    expect(graph.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({
        confidence: "source_declared",
        kind: "declared_parent",
      }),
    ]));
    expect(artifact.summary).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Source-declared edges", value: 1 }),
    ]));
    expect(artifact.limits.map((limit) => limit.code)).toContain("DECLARED_RELATIONSHIPS_REQUIRE_SOURCE_REVIEW");
  });
});
