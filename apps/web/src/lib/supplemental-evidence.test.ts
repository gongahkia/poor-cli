import { describe, expect, it } from "vitest";

import { buildSupplementalEvidenceReviewItems } from "@/lib/supplemental-evidence";
import type { BusinessDossier } from "@/types/dossier";

const baseDossier = {
  evidence: [],
  freshness: [],
  gaps: [],
  limits: [],
  provenance: [],
  records: {},
  summary: [],
  title: "ACME PTE LTD",
} satisfies BusinessDossier;

describe("supplemental evidence review items", () => {
  it("labels configured provider no-results without treating them as clearance", () => {
    const dossier = {
      ...baseDossier,
      records: {
        externalDiligence: [{
          title: "Sanctions Screen",
          summary: [{ label: "Candidate matches", value: 0, source: "OpenSanctions" }],
          gaps: [],
          limits: [{ code: "CANDIDATE_SCREEN_ONLY", message: "Matches are candidates for analyst review." }],
        }],
      },
      sourceCoverage: [{
        authRequired: true,
        coverageLevel: "full",
        family: "opensanctions",
        label: "OpenSanctions candidate screening",
        reason: "OpenSanctions screening completed.",
        recordCount: 0,
        status: "checked",
        tools: ["sg_sanctions_screen"],
      }],
    } satisfies BusinessDossier;

    const item = buildSupplementalEvidenceReviewItems({ dossier }).find((row) => row.id === "opensanctions");

    expect(item).toMatchObject({
      outcome: "no_result",
      providerState: "configured",
      recordCount: 0,
    });
    expect(item?.caveat).toContain("not sanctions clearance");
    expect(item?.confidenceLabel).toContain("Not a regulated sanctions determination");
    expect(item?.evidenceLabels).toEqual(expect.arrayContaining(["Third-party provider", "Not official registry fact", "Analyst-review only"]));
  });

  it("labels provider candidate results for analyst review", () => {
    const dossier = {
      ...baseDossier,
      records: {
        externalDiligence: [{
          title: "OpenCorporates Cross-Links",
          summary: [{ label: "Candidate links", value: 2, source: "OpenCorporates" }],
          gaps: [],
          limits: [{ code: "NO_OWNERSHIP_CLAIM", message: "OpenCorporates candidates are not ownership findings." }],
        }],
      },
      sourceCoverage: [{
        authRequired: true,
        coverageLevel: "partial",
        family: "opencorporates",
        label: "OpenCorporates cross-links",
        reason: "OpenCorporates returned candidate links.",
        recordCount: 2,
        status: "checked",
        tools: ["sg_opencorporates_links"],
      }],
    } satisfies BusinessDossier;

    const item = buildSupplementalEvidenceReviewItems({ dossier }).find((row) => row.id === "opencorporates");

    expect(item).toMatchObject({
      outcome: "candidate_match",
      providerState: "configured",
      recordCount: 2,
    });
    expect(item?.confidenceLabel).toContain("Confirm against source rows");
    expect(item?.caveat).toContain("not ownership, control, or beneficial-owner evidence");
  });

  it("distinguishes unconfigured, error, and rate-limited provider states", () => {
    const dossier = {
      ...baseDossier,
      records: {
        externalDiligence: [{
          title: "Adverse Media Lite",
          summary: [{ label: "Feed items matched", value: 0, source: "Official feeds" }],
          gaps: [{ code: "GOV_FEED_UNAVAILABLE", message: "Gov feed returned HTTP 500." }],
          limits: [],
        }],
      },
      sourceCoverage: [
        {
          authRequired: true,
          coverageLevel: "none",
          family: "opencorporates",
          gapCodes: ["OPENCORPORATES_API_TOKEN_REQUIRED"],
          label: "OpenCorporates cross-links",
          reason: "OpenCorporates API token is required.",
          recordCount: 0,
          requiredCredentials: ["OPENCORPORATES_API_TOKEN"],
          status: "credential_blocked",
          tools: ["sg_opencorporates_links"],
        },
        {
          authRequired: false,
          coverageLevel: "none",
          family: "adverse_media_lite",
          gapCodes: ["GOV_FEED_UNAVAILABLE"],
          label: "Adverse-media lite",
          reason: "Official public feed returned HTTP 500.",
          recordCount: 0,
          status: "unavailable",
          tools: ["sg_adverse_media_lite"],
        },
        {
          authRequired: true,
          coverageLevel: "none",
          family: "opensanctions",
          gapCodes: ["OPENSANCTIONS_UPSTREAM_FAILED"],
          label: "OpenSanctions candidate screening",
          reason: "OpenSanctions API returned HTTP 429 rate limit.",
          recordCount: 0,
          status: "unavailable",
          tools: ["sg_sanctions_screen"],
        },
      ],
    } satisfies BusinessDossier;

    const items = buildSupplementalEvidenceReviewItems({ dossier });

    expect(items.find((item) => item.id === "opencorporates")?.providerState).toBe("unconfigured");
    expect(items.find((item) => item.id === "adverse_media_lite")?.providerState).toBe("error");
    expect(items.find((item) => item.id === "opensanctions")?.providerState).toBe("rate_limited");
  });

  it("describes relationship graph links as explicit source-declared evidence only", () => {
    const dossier = {
      ...baseDossier,
      records: {
        externalDiligence: [{
          title: "Relationship Graph",
          summary: [
            { label: "Source-declared edges", value: 1, source: "Graph builder" },
            { label: "Inferred ownership/control edges", value: 0, source: "Graph builder" },
          ],
          gaps: [],
          limits: [{ code: "NO_INFERRED_OWNERSHIP_OR_CONTROL", message: "No ownership/control is inferred." }],
        }],
      },
      sourceCoverage: [{
        authRequired: false,
        coverageLevel: "partial",
        family: "relationship_graph",
        label: "Relationship graph",
        reason: "Graph built from supplied source-declared links.",
        recordCount: 1,
        status: "checked",
        tools: ["sg_relationship_graph"],
      }],
    } satisfies BusinessDossier;

    const item = buildSupplementalEvidenceReviewItems({ dossier }).find((row) => row.id === "relationship_graph");

    expect(item).toMatchObject({
      outcome: "candidate_match",
      providerState: "configured",
      recordCount: 1,
    });
    expect(item?.caveat).toContain("does not infer beneficial ownership or control");
    expect(item?.limitationLabel).toContain("No beneficial ownership, control");
  });
});
