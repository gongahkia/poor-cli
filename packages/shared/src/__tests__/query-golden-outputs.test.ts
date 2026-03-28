import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { QueryOutcomeSchema } from "../index.js";

const readGolden = (name: string) => {
  const url = new URL(`../../../../examples/golden-outputs/${name}`, import.meta.url);
  return JSON.parse(readFileSync(url, "utf8"));
};

describe("query golden outputs", () => {
  it("keeps the completed query golden schema-valid", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-completed.json"));

    expect(payload.status).toBe("completed");
    if (payload.status === "completed") {
      expect(payload.steps[0]?.tool).toBe("sg_onemap_reverse_geocode");
      expect(payload.continuationHints?.[0]).toContain("sg://");
    }
  });

  it("keeps the blocked query golden schema-valid", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-blocked.json"));

    expect(payload.status).toBe("blocked");
    if (payload.status === "blocked") {
      expect(payload.blockers[0]?.field).toBe("lat");
      expect(payload.routingExplanation).toContain("sg_onemap_reverse_geocode");
    }
  });

  it("keeps the unsupported query golden schema-valid", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-unsupported.json"));

    expect(payload.status).toBe("unsupported");
    if (payload.status === "unsupported") {
      expect(payload.reason).toContain("single-step direct executions");
    }
  });

  it("keeps the failed query golden schema-valid", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-failed.json"));

    expect(payload.status).toBe("failed");
    if (payload.status === "failed") {
      expect(payload.failedStep?.tool).toBe("sg_datagov_get");
    }
  });

  it("keeps the architecture-firm diligence golden believable", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-architecture-firm-diligence.json"));

    expect(payload.status).toBe("completed");
    if (payload.status === "completed") {
      expect(payload.workflow).toBe("architecture_firm_diligence");
      expect(payload.toolsUsed).toEqual(["sg_business_dossier"]);
      expect(payload.resultSummary?.headline).toContain("BOA");
    }
  });

  it("keeps the healthcare-supplier diligence golden believable", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-healthcare-supplier-diligence.json"));

    expect(payload.status).toBe("completed");
    if (payload.status === "completed") {
      expect(payload.workflow).toBe("healthcare_supplier_diligence");
      expect(payload.nextActions?.[0]?.tool).toBe("sg_hsa_licensed_pharmacies");
      expect(payload.resultSummary?.headline).toContain("HSA");
    }
  });

  it("keeps the hotel-operator lookup golden believable", () => {
    const payload = QueryOutcomeSchema.parse(readGolden("query-hotel-operator-lookup.json"));

    expect(payload.status).toBe("completed");
    if (payload.status === "completed") {
      expect(payload.workflow).toBe("hotel_operator_lookup");
      expect(payload.toolsUsed).toEqual(["sg_hlb_hotels"]);
      expect(payload.resultSummary?.headline).toContain("HLB");
    }
  });
});
