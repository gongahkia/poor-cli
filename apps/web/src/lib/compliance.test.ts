import { describe, expect, it } from "vitest";

import {
  buildComplianceUseLimitations,
  buildComplianceUseSummary,
  COMPLIANCE_USE_NOTICE,
  PDPA_RULE_MAPPING_NOTICE,
  PUBLIC_DATA_LIMITS_NOTICE,
} from "@/lib/compliance";

describe("compliance-use limitations", () => {
  it("keeps the standard non-advice clauses explicit", () => {
    expect(COMPLIANCE_USE_NOTICE).toContain("not legal");
    expect(COMPLIANCE_USE_NOTICE).toContain("licensed compliance advice");
    expect(PDPA_RULE_MAPPING_NOTICE).toContain("PDPA");
    expect(PDPA_RULE_MAPPING_NOTICE).toContain("not a legal opinion");
    expect(PUBLIC_DATA_LIMITS_NOTICE).toContain("Missing public-data evidence is a gap");
  });

  it("builds the export payload shared by JSON, CSV, and PDF surfaces", () => {
    expect(buildComplianceUseLimitations()).toMatchInlineSnapshot(`
      {
        "complianceUseNotice": "Dude maps public-data evidence to operational review questions only. It is not legal, tax, credit, investment, financial, or licensed compliance advice.",
        "pdpaRuleMappingNotice": "PDPA and rules-pack references are checklist prompts for a qualified reviewer; they are not a legal opinion on whether an organisation complies with PDPA or any other law.",
        "publicDataLimitsNotice": "Missing public-data evidence is a gap, not proof that a counterparty is clean, approved, conflict-free, sanctioned-free, or risk-free.",
      }
    `);
    expect(buildComplianceUseSummary()).toContain("Compliance use:");
    expect(buildComplianceUseSummary()).toContain("Public-data limits:");
  });
});
