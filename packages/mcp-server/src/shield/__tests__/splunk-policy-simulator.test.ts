import { describe, expect, it } from "vitest";
import {
  buildSplunkRedTeamMatrix,
  extractSplunkQueryIndexes,
  hashSplunkApprovalRequest,
  simulateSplunkSearchPolicy,
} from "../splunk-policy-simulator.js";

describe("Splunk policy simulator", () => {
  it("extracts SPL indexes and allows bounded allowlisted searches", () => {
    expect(extractSplunkQueryIndexes("index=security failed login index=main")).toEqual(["security", "main"]);

    const simulation = simulateSplunkSearchPolicy({
      query: "index=security failed login",
      earliest: "-24h",
      latest: "now",
      limit: 25,
    }, { allowedIndexes: ["security"] });

    expect(simulation).toMatchObject({
      status: "allow",
      riskScore: 10,
      ruleCodes: ["bounded_query"],
    });
  });

  it("denies destructive SPL and disallowed indexes", () => {
    expect(simulateSplunkSearchPolicy({
      query: "index=security | outputlookup secrets.csv",
      earliest: "-24h",
      latest: "now",
      limit: 10,
    }, { allowedIndexes: ["security"] }).status).toBe("deny");

    expect(simulateSplunkSearchPolicy({
      query: "index=_internal error",
      earliest: "-24h",
      latest: "now",
      limit: 10,
    }, { allowedIndexes: ["security"] }).ruleCodes).toContain("index_not_allowlisted");
  });

  it("requires approval for broad or unbounded searches", () => {
    const simulation = simulateSplunkSearchPolicy({
      query: "index=* error",
      limit: 75,
    }, { allowedIndexes: ["security"] });

    expect(simulation.status).toBe("approval_required");
    expect(simulation.ruleCodes).toEqual(expect.arrayContaining(["wildcard_index", "missing_time_bounds", "large_result_limit"]));
    expect(simulation.suggestedSaferQuery).toContain("latest=now");
  });

  it("builds a passing red-team matrix and stable request hashes", () => {
    const matrix = buildSplunkRedTeamMatrix(["main", "security"]);

    expect(matrix.every((row) => row.simulation.status === row.expectedStatus)).toBe(true);
    expect(hashSplunkApprovalRequest({ query: " index=security failed login ", limit: 50 }))
      .toBe(hashSplunkApprovalRequest({ query: "index=security failed login", limit: 50 }));
  });
});
