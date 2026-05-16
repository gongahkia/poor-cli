export const COMPLIANCE_USE_NOTICE =
  "Dude maps public-data evidence to operational review questions only. It is not legal, tax, credit, investment, financial, or licensed compliance advice.";

export const PDPA_RULE_MAPPING_NOTICE =
  "PDPA and rules-pack references are checklist prompts for a qualified reviewer; they are not a legal opinion on whether an organisation complies with PDPA or any other law.";

export const PUBLIC_DATA_LIMITS_NOTICE =
  "Missing public-data evidence is a gap, not proof that a counterparty is clean, approved, conflict-free, sanctioned-free, or risk-free.";

export const complianceUseLimitations = [
  { label: "Compliance use", value: COMPLIANCE_USE_NOTICE },
  { label: "PDPA and rules packs", value: PDPA_RULE_MAPPING_NOTICE },
  { label: "Public-data limits", value: PUBLIC_DATA_LIMITS_NOTICE },
] as const;

export type ComplianceUseLimitations = {
  readonly complianceUseNotice: string;
  readonly pdpaRuleMappingNotice: string;
  readonly publicDataLimitsNotice: string;
};

export function buildComplianceUseLimitations(): ComplianceUseLimitations {
  return {
    complianceUseNotice: COMPLIANCE_USE_NOTICE,
    pdpaRuleMappingNotice: PDPA_RULE_MAPPING_NOTICE,
    publicDataLimitsNotice: PUBLIC_DATA_LIMITS_NOTICE,
  };
}

export function buildComplianceUseSummary(): string {
  return complianceUseLimitations.map((item) => `${item.label}: ${item.value}`).join(" ");
}
