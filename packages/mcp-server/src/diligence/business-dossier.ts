import type {
  BriefArtifact,
  BriefFreshnessItem,
  BriefLimit,
  BriefProvenanceItem,
  EvidenceGap,
  AnalystFollowUp,
  AnalystFollowUpEvidenceBasis,
  AnalystFollowUpPriority,
  AnalystFollowUpReasonCategory,
  HsaNormalizedHealthProductLicenseeRecord,
  MatchConfidence,
  NextCheck,
  RiskFlag,
  SourceCoverageItem,
} from "@swee-sg/shared";
import { getAcraEntities } from "../apis/acra/client.js";
import { getBcaLicensedBuilders, getBcaRegisteredContractors } from "../apis/bca/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../apis/boa/client.js";
import { getCeaSalespersons } from "../apis/cea/client.js";
import { getGeBIZTenders } from "../apis/gebiz/client.js";
import { getHlbHotels } from "../apis/hlb/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../apis/hsa/client.js";
import type { BusinessDossierModule, BusinessSectorHint, InferredBusinessSector } from "./entity-resolution.js";
import {
  ALL_BUSINESS_DOSSIER_MODULES,
  getBusinessModulesForSector,
  inferBusinessSectorsFromAcra,
  resolveEntityMatchConfidence,
  selectBusinessDossierModules,
} from "./entity-resolution.js";
import {
  buildAdverseMediaLiteArtifact,
  buildOpenCorporatesLinksArtifact,
  buildRelationshipGraphArtifact,
  buildSanctionsScreenArtifact,
} from "./external-diligence.js";
import {
  SG_RISK_RULES_LAST_REVIEWED,
  SG_RISK_RULES_SCHEMA_VERSION,
  SG_RISK_RULES_SOURCE,
  SG_RISK_RULES_VERSION,
} from "./risk-rules.js";

type BusinessDossierParams = Readonly<{
  entityName?: string | undefined;
  uen?: string | undefined;
  salespersonName?: string | undefined;
  registrationNo?: string | undefined;
  estateAgentName?: string | undefined;
  estateAgentLicenseNo?: string | undefined;
  classCode?: string | undefined;
  workhead?: string | undefined;
  grade?: string | undefined;
  modules?: readonly BusinessDossierModule[] | undefined;
  sectorHints?: readonly BusinessSectorHint[] | undefined;
  explicitSectorHints?: readonly BusinessSectorHint[] | undefined;
  webSectorHints?: readonly BusinessSectorHint[] | undefined;
  analystRerun?: boolean | undefined;
  includeExternalDiligence?: boolean | undefined;
}>;

const toGap = (code: string, message: string): EvidenceGap => ({ code, message });
const toLimit = (code: string, message: string): BriefLimit => ({ code, message });
const PROVENANCE_SOURCE_URLS: Record<string, string> = {
  sg_acra_entities: "https://www.acra.gov.sg/resources/open-data-initiative/",
  sg_bca_licensed_builders: "https://developers.data.gov.sg/datasets?resultId=d_19573c579879be15623f2e1e3854926d",
  sg_bca_registered_contractors: "https://developers.data.gov.sg/datasets?resultId=d_dcda79be4aded5f9e769b8e23ff69b47",
  sg_cea_salespersons: "https://developers.data.gov.sg/datasets?resultId=d_07c63be0f37e6e59c07a4ddc2fd87fcb",
  sg_gebiz_tenders: "https://developers.data.gov.sg/datasets?resultId=d_c9bea4c28194866ab2e1313e6be430d6",
  sg_boa_architects: "https://developers.data.gov.sg/datasets?resultId=d_d77de0f78ca589a5c61da7a60fdee6ba",
  sg_boa_architecture_firms: "https://developers.data.gov.sg/datasets?resultId=d_d5c0a4ffd076a3e40d772275619bbb66",
  sg_hsa_licensed_pharmacies: "https://www.hsa.gov.sg/e-services/infosearch",
  sg_hsa_health_product_licensees: "https://www.hsa.gov.sg/e-services/infosearch",
  sg_hlb_hotels: "https://www.hlb.gov.sg/",
};

const safeRead = async <T>(
  code: string,
  message: string,
  read: () => Promise<T>,
  gaps: EvidenceGap[],
): Promise<T | null> => {
  try {
    return await read();
  } catch (error) {
    gaps.push(toGap(code, `${message}: ${error instanceof Error ? error.message : String(error)}`));
    return null;
  }
};

const toProvenance = (
  source: string,
  tool: string,
  coverage: string,
  authRequired: boolean,
  recordCount: number,
): BriefProvenanceItem => {
  const sourceUrl = PROVENANCE_SOURCE_URLS[tool];

  return {
    source,
    tool,
    coverage,
    authRequired,
    recordCount,
    ...(sourceUrl === undefined ? {} : { sourceUrl }),
    evidenceType: "official_registry",
  };
};

const toFreshness = (
  source: string,
  observedAt: string,
  upstreamTimestamp: string | null,
): BriefFreshnessItem => ({
  source,
  observedAt,
  upstreamTimestamp,
});

type CoverageFamilyDefinition = Readonly<{
  family: string;
  label: string;
  tools: readonly string[];
  authRequired: boolean;
  evidenceType: NonNullable<BriefProvenanceItem["evidenceType"]>;
  requiredCredentials?: readonly string[];
}>;

const OFFICIAL_COVERAGE_FAMILIES = {
  acra: {
    authRequired: false,
    evidenceType: "official_registry",
    family: "acra",
    label: "ACRA entity identity",
    tools: ["sg_acra_entities"],
  },
  bca: {
    authRequired: false,
    evidenceType: "official_registry",
    family: "bca",
    label: "BCA construction registries",
    tools: ["sg_bca_licensed_builders", "sg_bca_registered_contractors"],
  },
  boa: {
    authRequired: false,
    evidenceType: "official_registry",
    family: "boa",
    label: "BOA architecture registries",
    tools: ["sg_boa_architects", "sg_boa_architecture_firms"],
  },
  cea: {
    authRequired: false,
    evidenceType: "official_registry",
    family: "cea",
    label: "CEA estate-agent registry",
    tools: ["sg_cea_salespersons"],
  },
  gebiz: {
    authRequired: false,
    evidenceType: "official_registry",
    family: "gebiz",
    label: "GeBIZ procurement awards",
    tools: ["sg_gebiz_tenders"],
  },
  hlb: {
    authRequired: false,
    evidenceType: "official_registry",
    family: "hlb",
    label: "HLB hotel licensing",
    tools: ["sg_hlb_hotels"],
  },
  hsa: {
    authRequired: false,
    evidenceType: "official_registry",
    family: "hsa",
    label: "HSA healthcare licensing",
    tools: ["sg_hsa_licensed_pharmacies", "sg_hsa_health_product_licensees"],
  },
} as const satisfies Record<BusinessDossierModule, CoverageFamilyDefinition>;

type SectorWorkflowGuideItem = Readonly<{
  sector: BusinessSectorHint;
  label: string;
  retainedModules: readonly BusinessDossierModule[];
  retainedTools: readonly string[];
  whyRelevant: string;
  requiredIdentifiers: readonly string[];
  followUpPrompts: readonly string[];
  sourceBoundUse: string;
}>;

const SECTOR_WORKFLOW_GUIDE = [
  {
    sector: "construction",
    label: "Construction and builders",
    retainedModules: ["bca"],
    retainedTools: ["sg_bca_licensed_builders", "sg_bca_registered_contractors"],
    whyRelevant: "BCA licensed-builder and registered-contractor rows can support construction-sector diligence when the counterparty appears to carry out building or contractor activity.",
    requiredIdentifiers: [
      "Company name or UEN",
      "BCA licensed-builder class code, for example GB1",
      "BCA registered-contractor workhead and grade, for example CW01 / B2",
    ],
    followUpPrompts: [
      "Rerun with the exact UEN or registered construction company name.",
      "If the BCA class code, workhead, or grade is known, rerun the BCA module with that identifier.",
    ],
    sourceBoundUse: "Use BCA rows only as public registry evidence for the matching source record; no licensing opinion is inferred from no-match or skipped coverage.",
  },
  {
    sector: "architecture",
    label: "Architecture firms and architects",
    retainedModules: ["boa"],
    retainedTools: ["sg_boa_architecture_firms", "sg_boa_architects"],
    whyRelevant: "BOA firm and architect registries can support architecture-firm diligence where the counterparty or named professional appears in the retained BOA datasets.",
    requiredIdentifiers: [
      "Architecture firm name",
      "Architect name or BOA registration number",
    ],
    followUpPrompts: [
      "Rerun with the exact architecture-firm name shown in source material.",
      "If an individual architect is in scope, rerun with the BOA registration number or architect name.",
    ],
    sourceBoundUse: "Use BOA rows only for source-backed firm or architect matches; absence of a BOA row is not a conclusion about all architectural activity.",
  },
  {
    sector: "real_estate",
    label: "Real estate agencies and salespersons",
    retainedModules: ["cea"],
    retainedTools: ["sg_cea_salespersons"],
    whyRelevant: "CEA salesperson and estate-agent records can support real-estate diligence when an agency, salesperson, registration number, or licence number is in scope.",
    requiredIdentifiers: [
      "CEA salesperson registration number, for example R123456A",
      "Estate-agent licence number, for example L3000001A",
      "Salesperson name or estate-agent name",
    ],
    followUpPrompts: [
      "Rerun with the CEA registration number when reviewing an individual salesperson.",
      "Rerun with the estate-agent licence number or estate-agent name when reviewing an agency.",
    ],
    sourceBoundUse: "Use CEA rows as official registry evidence for matched salespersons or estate agents; no-match coverage is a source gap, not a clearance.",
  },
  {
    sector: "healthcare",
    label: "Healthcare suppliers and pharmacies",
    retainedModules: ["hsa"],
    retainedTools: ["sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies"],
    whyRelevant: "HSA health-product licensee and licensed-pharmacy rows can support healthcare-sector diligence for suppliers, importers, wholesalers, manufacturers, or pharmacies.",
    requiredIdentifiers: [
      "Company or pharmacy name",
      "HSA licence type or licence reference if available",
      "Pharmacist-in-charge, address, or postal code for pharmacy checks if available",
    ],
    followUpPrompts: [
      "Rerun with the exact company name used on the HSA health-product licence.",
      "For pharmacy checks, rerun with the pharmacy name or a tighter pharmacy identifier.",
    ],
    sourceBoundUse: "Use HSA rows only for matched licence or pharmacy evidence; a match does not imply every product or site is covered.",
  },
  {
    sector: "hospitality",
    label: "Hotels and keepers",
    retainedModules: ["hlb"],
    retainedTools: ["sg_hlb_hotels"],
    whyRelevant: "HLB hotel and keeper rows can support hospitality diligence where a hotel name, keeper, or operator appears in the retained hotels dataset.",
    requiredIdentifiers: [
      "Hotel name",
      "Hotel keeper or operator name",
      "Hotel address or postal code if available",
    ],
    followUpPrompts: [
      "Rerun with the exact hotel name if the operator name did not match.",
      "Rerun with the keeper or operator name shown in source material.",
    ],
    sourceBoundUse: "Use HLB rows as hotel or keeper evidence only; a keeper match is not a full hospitality licensing opinion.",
  },
  {
    sector: "procurement",
    label: "Public procurement suppliers",
    retainedModules: ["gebiz"],
    retainedTools: ["sg_gebiz_tenders"],
    whyRelevant: "GeBIZ award rows can support procurement diligence where the counterparty may have supplied goods or services to Singapore public-sector buyers.",
    requiredIdentifiers: [
      "Supplier or entity name used in GeBIZ awards",
      "Tender agency, category, or procurement terms if narrowing is needed",
    ],
    followUpPrompts: [
      "Rerun with the exact supplier name used in award notices.",
      "If the supplier name is broad, follow up with agency, category, or tender terms in a direct GeBIZ check.",
    ],
    sourceBoundUse: "Use GeBIZ rows only as public procurement award evidence; no-match coverage does not rule out subcontracting or differently named supplier records.",
  },
] as const satisfies readonly SectorWorkflowGuideItem[];

const sectorGuideForModule = (
  module: BusinessDossierModule,
): SectorWorkflowGuideItem | undefined =>
  SECTOR_WORKFLOW_GUIDE.find((item) => (item.retainedModules as readonly BusinessDossierModule[]).includes(module));

const moduleRequiredIdentifierText = (
  module: BusinessDossierModule,
): string => {
  if (module === "acra") {
    return "company name or UEN";
  }
  return sectorGuideForModule(module)?.requiredIdentifiers.join("; ") ?? "a source-specific identifier";
};

const needsIdentifierGapCode = (module: BusinessDossierModule): string =>
  `${module.toUpperCase()}_NEEDS_IDENTIFIER`;

const buildNeedsIdentifierGap = (
  module: BusinessDossierModule,
): EvidenceGap => toGap(
  needsIdentifierGapCode(module),
  `${OFFICIAL_COVERAGE_FAMILIES[module].label} was selected but not searched because the dossier needs ${moduleRequiredIdentifierText(module)}. Rerun with an explicit sector hint and the source-specific identifier before treating this sector as reviewed.`,
);

const SUPPLEMENTAL_COVERAGE_FAMILIES = [
  {
    artifactTitle: "Sanctions Screen",
    definition: {
      authRequired: true,
      evidenceType: "web_discovery",
      family: "opensanctions",
      label: "OpenSanctions candidate screen",
      requiredCredentials: ["OPENSANCTIONS_API_KEY"],
      tools: ["sg_sanctions_screen"],
    },
  },
  {
    artifactTitle: "OpenCorporates Cross-Links",
    definition: {
      authRequired: true,
      evidenceType: "web_discovery",
      family: "opencorporates",
      label: "OpenCorporates cross-links",
      requiredCredentials: ["OPENCORPORATES_API_TOKEN"],
      tools: ["sg_opencorporates_links"],
    },
  },
  {
    artifactTitle: "Adverse Media Lite",
    definition: {
      authRequired: false,
      evidenceType: "web_discovery",
      family: "adverse_media_lite",
      label: "Adverse-media lite official feeds",
      tools: ["sg_adverse_media_lite"],
    },
  },
  {
    artifactTitle: "Relationship Graph",
    definition: {
      authRequired: false,
      evidenceType: "web_discovery",
      family: "relationship_graph",
      label: "Relationship graph",
      tools: ["sg_relationship_graph"],
    },
  },
] as const;

const ORCHESTRATOR_ONLY_COVERAGE_FAMILIES = [
  {
    authRequired: true,
    evidenceType: "web_discovery",
    family: "web_presence",
    label: "Web presence",
    requiredCredentials: ["TINYFISH_API_KEY"],
    tools: ["TinyFish Search"],
  },
  {
    authRequired: true,
    evidenceType: "web_discovery",
    family: "people_discovery",
    label: "People discovery",
    requiredCredentials: ["TINYFISH_API_KEY"],
    tools: ["TinyFish Search"],
  },
] as const satisfies readonly CoverageFamilyDefinition[];

const UNAVAILABLE_GAP_PATTERNS: Readonly<Record<string, RegExp>> = {
  sg_acra_entities: /^ACRA_UNAVAILABLE$/,
  sg_bca_licensed_builders: /^BCA_BUILDERS_UNAVAILABLE$/,
  sg_bca_registered_contractors: /^BCA_CONTRACTORS_UNAVAILABLE$/,
  sg_boa_architects: /^BOA_ARCHITECTS_UNAVAILABLE$/,
  sg_boa_architecture_firms: /^BOA_FIRMS_UNAVAILABLE$/,
  sg_cea_salespersons: /^CEA_UNAVAILABLE$/,
  sg_gebiz_tenders: /^GEBIZ_UNAVAILABLE$/,
  sg_hlb_hotels: /^HLB_UNAVAILABLE$/,
  sg_hsa_licensed_pharmacies: /^HSA_PHARMACIES_UNAVAILABLE$/,
  sg_hsa_health_product_licensees: /^HSA_LICENSEES_UNAVAILABLE$/,
};

const GAP_MODULE_PREFIXES: Record<BusinessDossierModule, RegExp> = {
  acra: /^ACRA_/,
  bca: /^BCA_/,
  boa: /^BOA_/,
  cea: /^CEA_/,
  gebiz: /^GEBIZ_/,
  hlb: /^HLB_/,
  hsa: /^HSA_/,
};

const getFirstTimestamp = (
  records: readonly Readonly<Record<string, unknown>>[] | null,
  fields: readonly string[],
): string | null => {
  if (records === null) return null;
  for (const record of records) {
    for (const field of fields) {
      const value = record[field];
      if (typeof value === "string" && value.trim() !== "") {
        return value;
      }
    }
  }
  return null;
};

const buildBusinessRiskFlags = (
  params: Pick<BusinessDossierParams, "entityName" | "uen">,
  searchedModules: ReadonlySet<BusinessDossierModule>,
  acra: readonly Readonly<Record<string, unknown>>[],
  builders: readonly Readonly<Record<string, unknown>>[],
  contractors: readonly Readonly<Record<string, unknown>>[],
  hsaLicensees: readonly HsaNormalizedHealthProductLicenseeRecord[],
): readonly RiskFlag[] => {
  const flags: RiskFlag[] = [];
  const primary = acra[0];
  if (primary !== undefined) {
    const status = String(primary["entityStatusDescription"] ?? "").toLowerCase();
    if (status !== "" && !status.includes("live") && !status.includes("registered")) {
      flags.push({
        code: "ENTITY_NOT_ACTIVE",
        severity: "high",
        message: `Entity status is "${primary["entityStatusDescription"]}", not Live or Registered.`,
        source: "ACRA",
      });
    }
  }
  if (
    searchedModules.has("acra")
    && (params.entityName !== undefined || params.uen !== undefined)
    && acra.length === 0
  ) {
    flags.push({
      code: "NO_ACRA_MATCH",
      severity: "high",
      message: "No ACRA entity matched the provided identifier.",
      source: "ACRA",
    });
  }
  for (const record of builders) {
    const expiry = record["expiryDate"];
    if (typeof expiry === "string" && expiry.trim() !== "") {
      const expiryDate = new Date(expiry);
      if (!Number.isNaN(expiryDate.getTime()) && expiryDate < new Date()) {
        flags.push({
          code: "BUILDER_LICENSE_EXPIRED",
          severity: "high",
          message: `Builder license expired on ${expiry}.`,
          source: "BCA",
        });
      }
    }
  }
  for (const record of contractors) {
    const expiry = record["expiryDate"];
    if (typeof expiry === "string" && expiry.trim() !== "") {
      const expiryDate = new Date(expiry);
      if (!Number.isNaN(expiryDate.getTime()) && expiryDate < new Date()) {
        flags.push({
          code: "CONTRACTOR_EXPIRED",
          severity: "medium",
          message: `Contractor registration expired on ${expiry}.`,
          source: "BCA",
        });
      }
    }
  }
  for (const record of hsaLicensees) {
    if (record.expiryDate === null) continue;
    const expiryDate = new Date(record.expiryDate);
    if (!Number.isNaN(expiryDate.getTime()) && expiryDate < new Date()) {
      flags.push({
        code: "HEALTH_PRODUCT_LICENCE_EXPIRED",
        severity: "medium",
        message: `${record.licenseType} expired on ${record.expiryDate}.`,
        source: "HSA",
      });
    }
  }
  const acraName = typeof primary?.["entityName"] === "string" ? primary["entityName"] as string : null;
  if (acraName !== null) {
    const normalize = (s: unknown): string =>
      typeof s !== "string" ? "" : s.toLowerCase().replace(/[^a-z0-9]+/g, "").trim();
    const acraCanon = normalize(acraName);
    const otherNames: ReadonlyArray<{ source: string; name: string }> = [
      ...builders.map((r) => ({ source: "BCA builder", name: String(r["companyName"] ?? "") })),
      ...contractors.map((r) => ({ source: "BCA contractor", name: String(r["companyName"] ?? "") })),
      ...hsaLicensees.map((r) => ({ source: "HSA", name: String(r.companyName ?? "") })),
    ];
    for (const other of otherNames) {
      const otherCanon = normalize(other.name);
      if (otherCanon === "" || acraCanon === "") continue;
      if (otherCanon !== acraCanon && !otherCanon.includes(acraCanon) && !acraCanon.includes(otherCanon)) {
        flags.push({
          code: "CROSS_SOURCE_NAME_DIVERGENCE",
          severity: "medium",
          message: `ACRA entity name "${acraName}" does not match ${other.source} name "${other.name}".`,
          source: `ACRA/${other.source}`,
        });
        break; // one divergence flag is enough
      }
    }
  }
  return flags;
};

const buildBusinessNextChecks = (
  params: BusinessDossierParams,
  selectedModules: readonly BusinessDossierModule[],
): readonly NextCheck[] => {
  const checks: NextCheck[] = [];
  if (params.uen !== undefined) {
    checks.push({
      tool: "sg_acra_entities",
      reason: "Retrieve full ACRA entity details for deeper officer and status inspection.",
      input: { uen: params.uen },
    });
  }
  if (params.entityName !== undefined) {
    if (selectedModules.includes("bca")) {
      checks.push({
        tool: "sg_bca_licensed_builders",
        reason: "Inspect licensed-builder rows by company/UEN or BCA class code; capture class code and expiry evidence if returned.",
        input: { companyName: params.entityName, ...(params.uen === undefined ? {} : { uenNo: params.uen }), ...(params.classCode === undefined ? {} : { classCode: params.classCode }) },
      });
      checks.push({
        tool: "sg_bca_registered_contractors",
        reason: "Inspect registered-contractor rows by company/UEN, workhead, or grade; capture workhead/grade and expiry evidence if returned.",
        input: { companyName: params.entityName, ...(params.uen === undefined ? {} : { uenNo: params.uen }), ...(params.workhead === undefined ? {} : { workhead: params.workhead }), ...(params.grade === undefined ? {} : { grade: params.grade }) },
      });
    }
    if (selectedModules.includes("gebiz")) {
      checks.push({
        tool: "sg_gebiz_tenders",
        reason: "Inspect GeBIZ tender-award history for the named supplier; narrow later with agency, category, or tender terms if the supplier name is broad.",
        input: { supplierName: params.entityName },
      });
    }
    if (selectedModules.includes("boa")) {
      checks.push({
        tool: "sg_boa_architecture_firms",
        reason: "Inspect BOA architecture-firm records for the named entity; follow up separately with an architect name or BOA registration number where relevant.",
        input: { firmName: params.entityName },
      });
    }
    if (selectedModules.includes("hsa")) {
      checks.push({
        tool: "sg_hsa_health_product_licensees",
        reason: "Inspect HSA health-product licence rows for the named entity; capture licence type and expiry evidence if returned.",
        input: { companyName: params.entityName },
      });
      checks.push({
        tool: "sg_hsa_licensed_pharmacies",
        reason: "Check whether the named entity also appears as a licensed pharmacy; rerun with pharmacy name, address, or postal code if needed.",
        input: { pharmacyName: params.entityName },
      });
    }
    if (selectedModules.includes("hlb")) {
      checks.push({
        tool: "sg_hlb_hotels",
        reason: "Inspect hotel records by keeper or hotel name for the named entity.",
        input: { keeperName: params.entityName },
      });
    }
  }
  if (selectedModules.includes("cea") && (
    params.registrationNo !== undefined
    || params.estateAgentLicenseNo !== undefined
    || params.salespersonName !== undefined
    || params.estateAgentName !== undefined
    || params.entityName !== undefined
  )) {
    checks.push({
      tool: "sg_cea_salespersons",
      reason: "Inspect CEA salesperson or estate-agent rows by registration number, licence number, salesperson name, or estate-agent name.",
      input: Object.fromEntries(Object.entries({
        ...(params.registrationNo === undefined ? {} : { registrationNo: params.registrationNo }),
        ...(params.estateAgentLicenseNo === undefined ? {} : { estateAgentLicenseNo: params.estateAgentLicenseNo }),
        ...(params.salespersonName === undefined ? {} : { salespersonName: params.salespersonName }),
        estateAgentName: params.estateAgentName ?? params.entityName,
      }).filter(([, value]) => value !== undefined)),
    });
  }
  if (selectedModules.includes("boa") && params.registrationNo !== undefined) {
    checks.push({
      tool: "sg_boa_architects",
      reason: "Inspect BOA architect rows by registration number.",
      input: { registrationNo: params.registrationNo },
    });
  }
  if (params.entityName !== undefined || params.uen !== undefined) {
    checks.push({
      tool: "sg_sanctions_screen",
      reason: "Screen candidate sanctions/watchlist matches with OpenSanctions when a licensed API key is configured.",
      input: { name: params.entityName ?? params.uen ?? "", ...(params.uen === undefined ? {} : { uen: params.uen }) },
    });
    checks.push({
      tool: "sg_opencorporates_links",
      reason: "Cross-link the entity to OpenCorporates identifiers without inferring ownership or control.",
      input: { entityName: params.entityName ?? params.uen ?? "", ...(params.uen === undefined ? {} : { uen: params.uen }), jurisdictionCode: "sg" },
    });
    checks.push({
      tool: "sg_adverse_media_lite",
      reason: "Search bounded official Singapore public feeds for keyword evidence.",
      input: { keyword: params.entityName ?? params.uen ?? "" },
    });
    checks.push({
      tool: "sg_relationship_graph",
      reason: "Build a shallow graph from supplied dossier records, including explicit source-declared relationships when present, with strict limits against inferred ownership or control.",
      input: { records: "Use this dossier's records object." },
    });
  }
  return checks;
};

type AnalystFollowUpDraft = Omit<AnalystFollowUp, "id">;

const MAX_ANALYST_FOLLOW_UPS = 6;

const PRIORITY_RANK: Record<AnalystFollowUpPriority, number> = {
  critical: 0,
  recommended: 1,
  optional: 2,
};

const CATEGORY_RANK: Record<AnalystFollowUpReasonCategory, number> = {
  identity_confidence: 0,
  source_unavailable: 1,
  credential_required: 2,
  sector_gap: 3,
  supplemental_review: 4,
  manual_confirmation: 5,
  report_quality: 6,
};

const slugId = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "follow-up";

const followUpId = (index: number, followUp: AnalystFollowUpDraft): string =>
  `follow-up-${String(index + 1).padStart(2, "0")}-${followUp.priority}-${slugId(followUp.category)}-${slugId(followUp.evidenceBasis[0]?.ref ?? followUp.action)}`;

const followUpToolInput = (
  tool: string | undefined,
  input: Readonly<Record<string, unknown>> | undefined,
): Pick<AnalystFollowUpDraft, "input" | "tool"> => ({
  ...(input === undefined ? {} : { input }),
  ...(tool === undefined ? {} : { tool }),
});

const buildCoverageFollowUp = (
  item: SourceCoverageItem,
  nextCheckByTool: ReadonlyMap<string, NextCheck>,
): AnalystFollowUpDraft | null => {
  if (item.status === "not_applicable") {
    return null;
  }

  const nextCheck = item.tools.map((tool) => nextCheckByTool.get(tool)).find((check) => check !== undefined);
  const hasOfficialGap = item.evidenceType !== "web_discovery";
  const officialModule = ALL_BUSINESS_DOSSIER_MODULES.find((module) => OFFICIAL_COVERAGE_FAMILIES[module].family === item.family);
  const sectorGuide = officialModule === undefined ? undefined : sectorGuideForModule(officialModule);
  const identifierPrompt = sectorGuide === undefined
    ? "a source-specific identifier"
    : sectorGuide.requiredIdentifiers.join("; ");
  const basisKind: AnalystFollowUpEvidenceBasis["kind"] = item.status === "skipped"
    ? "skipped_module"
    : "source_gap";
  const basis: AnalystFollowUpEvidenceBasis = {
    detail: item.reason,
    kind: basisKind,
    ref: `sourceCoverage.${item.family}`,
    source: item.label,
  };

  if (item.status === "credential_blocked") {
    return {
      action: `Configure access for ${item.label} or record that the source was unavailable in this review.`,
      category: "credential_required",
      evidenceBasis: [basis],
      priority: item.family === "web_presence" || item.family === "people_discovery" ? "recommended" : "critical",
      reason: item.requiredCredentials === undefined || item.requiredCredentials.length === 0
        ? `${item.label} was blocked by missing source access.`
        : `${item.label} was blocked by missing credential(s): ${item.requiredCredentials.join(", ")}.`,
      whyThisMatters: "The dossier is missing a configured source family, so reviewers should not treat the absent provider output as reviewed evidence.",
      ...followUpToolInput(nextCheck?.tool ?? item.tools.find((tool) => !/tinyfish/i.test(tool)), nextCheck?.input),
    };
  }

  if (item.status === "unavailable" || item.coverageLevel === "partial") {
    return {
      action: `Retry ${item.label} source lookup or record the unresolved provider gap in the analyst file.`,
      category: "source_unavailable",
      evidenceBasis: [basis],
      priority: item.family === "acra" ? "critical" : "recommended",
      reason: item.gapCodes === undefined || item.gapCodes.length === 0
        ? item.reason
        : `${item.reason} Gap code(s): ${item.gapCodes.join(", ")}.`,
      whyThisMatters: "A failed or partial source read limits the evidence base behind the current CDD summary.",
      ...followUpToolInput(nextCheck?.tool ?? item.tools.find((tool) => !/tinyfish/i.test(tool)), nextCheck?.input),
    };
  }

  if (item.status === "skipped") {
    const supplemental = item.evidenceType === "web_discovery";
    return {
      action: supplemental
        ? `Decide whether ${item.label} supplemental review is needed, then run it or document why it stayed out of scope.`
        : `Run ${item.label} with ${identifierPrompt} or document why this source family stayed out of scope.`,
      category: supplemental ? "supplemental_review" : "sector_gap",
      evidenceBasis: [basis],
      priority: supplemental ? "optional" : "recommended",
      reason: item.reason,
      whyThisMatters: supplemental
        ? "Supplemental sources are analyst-review evidence only, but skipped coverage should remain visible in the review trail."
        : "A selected official source family did not run, so the report should show that the sector evidence is incomplete.",
      ...followUpToolInput(nextCheck?.tool ?? item.tools.find((tool) => !/tinyfish/i.test(tool)), nextCheck?.input),
    };
  }

  if (item.status === "checked" && item.recordCount === 0) {
    if (item.family === "acra") {
      return {
        action: "Confirm the counterparty name or UEN against ACRA source rows before using this dossier.",
        category: "identity_confidence",
        evidenceBasis: [basis],
        priority: "critical",
        reason: item.reason,
        whyThisMatters: "ACRA identity evidence is the gate for the rest of the CDD workflow.",
        ...followUpToolInput(nextCheck?.tool ?? "sg_acra_entities", nextCheck?.input),
      };
    }
    if (hasOfficialGap) {
      return {
        action: `Review whether ${item.label} needs ${identifierPrompt} for this counterparty.`,
        category: "sector_gap",
        evidenceBasis: [basis],
        priority: "recommended",
        reason: item.reason,
        whyThisMatters: "A zero-record official source result is missing public evidence, not a positive finding.",
        ...followUpToolInput(nextCheck?.tool ?? item.tools[0], nextCheck?.input),
      };
    }
    return {
      action: `Review ${item.label} results and note the source limitation in the analyst file.`,
      category: "supplemental_review",
      evidenceBasis: [basis],
      priority: "optional",
      reason: item.reason,
      whyThisMatters: "Supplemental search results can be incomplete, so absent snippets should not be overstated.",
      ...followUpToolInput(nextCheck?.tool ?? item.tools.find((tool) => !/tinyfish/i.test(tool)), nextCheck?.input),
    };
  }

  return null;
};

const buildGapFollowUp = (
  gap: EvidenceGap,
  nextCheckByTool: ReadonlyMap<string, NextCheck>,
): AnalystFollowUpDraft | null => {
  const basis: AnalystFollowUpEvidenceBasis = {
    detail: gap.message,
    kind: /RESOLUTION|ACRA|NO_MATCH/i.test(gap.code) ? "confidence_blocker" : "source_gap",
    ref: `gap.${gap.code}`,
    source: gap.code,
  };
  const acraCheck = nextCheckByTool.get("sg_acra_entities");

  if (/RESOLUTION_CONFIRMATION_REQUIRED|RESOLUTION_FUZZY_MATCH/i.test(gap.code)) {
    return {
      action: "Confirm the selected registry candidate against source rows before relying on this dossier.",
      category: "manual_confirmation",
      evidenceBasis: [basis],
      priority: "critical",
      reason: gap.message,
      whyThisMatters: "Ambiguous entity resolution can attach evidence to the wrong counterparty record.",
      ...followUpToolInput(acraCheck?.tool ?? "sg_acra_entities", acraCheck?.input),
    };
  }

  if (/RESOLUTION_NO_MATCH|NO_ACRA_MATCH|ACRA/i.test(gap.code)) {
    return {
      action: "Re-run ACRA identity lookup with the exact UEN or normalized company name.",
      category: "identity_confidence",
      evidenceBasis: [basis],
      priority: "critical",
      reason: gap.message,
      whyThisMatters: "The CDD summary depends on a source-backed counterparty identity before sector evidence is useful.",
      ...followUpToolInput(acraCheck?.tool ?? "sg_acra_entities", acraCheck?.input),
    };
  }

  if (/UNAVAILABLE|FAILED|TIMEOUT|RATE_LIMIT|HTTP/i.test(gap.code)) {
    return {
      action: "Retry the failed source module or record the provider gap in the analyst file.",
      category: "source_unavailable",
      evidenceBasis: [basis],
      priority: "recommended",
      reason: gap.message,
      whyThisMatters: "Provider failures leave source coverage incomplete and should remain visible to report reviewers.",
    };
  }

  return null;
};

const buildMatchConfidenceFollowUp = (
  match: MatchConfidence,
  nextCheckByTool: ReadonlyMap<string, NextCheck>,
): AnalystFollowUpDraft | null => {
  if (match.confidence === "exact" || match.confidence === "name-exact") {
    return null;
  }
  const basis: AnalystFollowUpEvidenceBasis = {
    detail: match.confidence === "name-fuzzy"
      ? `Bounded fuzzy match from ${match.source}${match.matchedOn === null ? "" : ` on ${match.matchedOn}`}.`
      : `No matching source row from ${match.source}.`,
    kind: "confidence_blocker",
    ref: `matchConfidence.${match.source}.${match.confidence}`,
    source: match.source,
  };
  const acraCheck = nextCheckByTool.get("sg_acra_entities");

  return {
    action: match.confidence === "name-fuzzy"
      ? `Manually confirm the ${match.source} matched row against the counterparty identifier.`
      : `Provide a more exact identifier for ${match.source} lookup.`,
    category: match.confidence === "name-fuzzy" ? "manual_confirmation" : "identity_confidence",
    evidenceBasis: [basis],
    priority: match.confidence === "name-fuzzy" ? "recommended" : "critical",
    reason: basis.detail,
    whyThisMatters: "Identity confidence affects how much weight the reviewer can place on the attached evidence.",
    ...followUpToolInput(
      match.source === "ACRA" ? acraCheck?.tool ?? "sg_acra_entities" : undefined,
      match.source === "ACRA" ? acraCheck?.input : undefined,
    ),
  };
};

const buildReportQualityFollowUp = (limit: BriefLimit): AnalystFollowUpDraft => ({
  action: "Carry this dossier limitation into the report notes before export.",
  category: "report_quality",
  evidenceBasis: [{
    detail: limit.message,
    kind: "evidence_limitation",
    ref: `limit.${limit.code}`,
    source: "Dossier limit",
  }],
  priority: "optional",
  reason: `${limit.code}: ${limit.message}`,
  whyThisMatters: "Report readers need the same evidence boundaries that constrained the generated CDD summary.",
});

const compareFollowUps = (left: AnalystFollowUpDraft, right: AnalystFollowUpDraft): number => {
  const priority = PRIORITY_RANK[left.priority] - PRIORITY_RANK[right.priority];
  if (priority !== 0) return priority;
  const category = CATEGORY_RANK[left.category] - CATEGORY_RANK[right.category];
  if (category !== 0) return category;
  const leftRef = left.evidenceBasis[0]?.ref ?? "";
  const rightRef = right.evidenceBasis[0]?.ref ?? "";
  const ref = leftRef.localeCompare(rightRef);
  if (ref !== 0) return ref;
  return left.action.localeCompare(right.action);
};

export const buildDossierAnalystFollowUps = (
  dossier: Pick<BriefArtifact, "gaps" | "limits" | "matchConfidence" | "nextChecks" | "sourceCoverage">,
): readonly AnalystFollowUp[] => {
  const nextCheckByTool = new Map((dossier.nextChecks ?? []).map((check) => [check.tool, check]));
  const drafts: AnalystFollowUpDraft[] = [
    ...(dossier.sourceCoverage ?? []).flatMap((item) => {
      const followUp = buildCoverageFollowUp(item, nextCheckByTool);
      return followUp === null ? [] : [followUp];
    }),
    ...dossier.gaps.flatMap((gap) => {
      const followUp = buildGapFollowUp(gap, nextCheckByTool);
      return followUp === null ? [] : [followUp];
    }),
    ...(dossier.matchConfidence ?? []).flatMap((match) => {
      const followUp = buildMatchConfidenceFollowUp(match, nextCheckByTool);
      return followUp === null ? [] : [followUp];
    }),
  ];
  const limit = dossier.limits.find((item) => item.code === "PUBLIC_DATA_ONLY")
    ?? dossier.limits.find((item) => item.code === "NO_CORPORATE_GRAPH")
    ?? dossier.limits[0];
  if (limit !== undefined) {
    drafts.push(buildReportQualityFollowUp(limit));
  }

  const deduped = new Map<string, AnalystFollowUpDraft>();
  for (const draft of drafts) {
    const key = `${draft.priority}:${draft.category}:${draft.tool ?? ""}:${draft.evidenceBasis.map((basis) => basis.ref).join("|")}`;
    if (!deduped.has(key)) {
      deduped.set(key, draft);
    }
  }

  return Array.from(deduped.values())
    .sort(compareFollowUps)
    .slice(0, MAX_ANALYST_FOLLOW_UPS)
    .map((followUp, index) => ({
      ...followUp,
      id: followUpId(index, followUp),
    }));
};

export const withDossierAnalystFollowUps = <
  T extends Pick<BriefArtifact, "gaps" | "limits" | "matchConfidence" | "nextChecks" | "sourceCoverage">,
>(dossier: T): T & { readonly analystFollowUps: readonly AnalystFollowUp[] } => ({
  ...dossier,
  analystFollowUps: buildDossierAnalystFollowUps(dossier),
});

const buildBusinessLimits = (
  selectedModules: readonly BusinessDossierModule[],
): readonly BriefLimit[] => [
  toLimit("EXACT_AND_BOUNDED_MATCHING", "Registry matching prioritizes exact identifiers, then exact normalized names, then bounded fuzzy-name checks."),
  toLimit("NO_CORPORATE_GRAPH", "This dossier does not infer directors, officers, shareholders, beneficial owners, subsidiaries, parent entities, or corporate control graphs."),
  toLimit("PUBLIC_DATA_ONLY", "The dossier only uses official public registries and datasets currently exposed through this server."),
  toLimit("PUBLIC_REGISTRY_SCOPE", `This dossier is limited to the selected module set: ${selectedModules.join(", ")}.`),
];

type ModuleReason = Readonly<{
  module: BusinessDossierModule;
  status: "matched" | "unmatched" | "needs_identifier" | "unsearched" | "skipped";
  selectedBy: readonly ("default" | "explicit_module" | "sector_hint" | "inferred_sector" | "web_hint" | "analyst_rerun")[];
  searched: boolean;
  matched: boolean;
  reason: string;
  sectorHints?: readonly BusinessSectorHint[];
  inferredSectors?: readonly BusinessSectorHint[];
  webSectorHints?: readonly BusinessSectorHint[];
  requiredIdentifiers?: readonly string[];
  followUpPrompts?: readonly string[];
}>;

const gapCodesForModule = (
  module: BusinessDossierModule,
  gaps: readonly EvidenceGap[],
): readonly string[] => gaps
  .filter((gap) => GAP_MODULE_PREFIXES[module].test(gap.code))
  .map((gap) => gap.code);

const unavailableToolCount = (
  tools: readonly string[],
  gapCodes: readonly string[],
): number => tools.filter((tool) => {
  const pattern = UNAVAILABLE_GAP_PATTERNS[tool];
  return pattern !== undefined && gapCodes.some((code) => pattern.test(code));
}).length;

const coverageRecordCount = (
  records: readonly (readonly unknown[])[],
): number => records.reduce((count, sourceRecords) => count + sourceRecords.length, 0);

const buildSourceCoverageItem = (
  definition: CoverageFamilyDefinition,
  values: Readonly<{
    status: SourceCoverageItem["status"];
    coverageLevel: SourceCoverageItem["coverageLevel"];
    recordCount: number;
    reason: string;
    checkedAt?: string | null;
    sourceFreshness?: string | null;
    gapCodes?: readonly string[];
  }>,
): SourceCoverageItem => ({
  authRequired: definition.authRequired,
  coverageLevel: values.coverageLevel,
  evidenceType: definition.evidenceType,
  family: definition.family,
  label: definition.label,
  recordCount: values.recordCount,
  reason: values.reason,
  status: values.status,
  tools: definition.tools,
  ...(values.checkedAt === undefined ? {} : { checkedAt: values.checkedAt }),
  ...(values.sourceFreshness === undefined ? {} : { sourceFreshness: values.sourceFreshness }),
  ...(definition.requiredCredentials === undefined ? {} : { requiredCredentials: definition.requiredCredentials }),
  ...(values.gapCodes === undefined || values.gapCodes.length === 0 ? {} : { gapCodes: values.gapCodes }),
});

const buildOfficialCoverageReason = (
  reason: ModuleReason,
  recordCount: number,
  status: SourceCoverageItem["status"],
  coverageLevel: SourceCoverageItem["coverageLevel"],
  unavailableCount: number,
): string => {
  if (reason.status === "needs_identifier") {
    return `${reason.reason} Treat this as an unchecked sector gap, not a clean result.`;
  }
  if (status === "not_applicable") {
    return `${reason.reason} No conclusion is drawn from this unchecked source family.`;
  }
  if (status === "skipped") {
    return `${reason.reason} Treat this as an unchecked coverage gap, not a clean result.`;
  }
  if (status === "unavailable") {
    return `Lookup was attempted but every source in this family failed or was unavailable. Treat this as a coverage gap, not a clean result.`;
  }
  if (coverageLevel === "partial") {
    return `Lookup was attempted and returned ${recordCount} public record(s), but ${unavailableCount} source tool(s) in the family failed or were unavailable. Partial coverage is not clearance.`;
  }
  if (recordCount === 0) {
    return `${reason.reason} No matching public records were returned; this is missing public evidence, not a positive clearance claim.`;
  }
  return `${reason.reason} Returned ${recordCount} public record(s).`;
};

const buildOfficialCoverageItems = (params: Readonly<{
  moduleReasons: readonly ModuleReason[];
  gaps: readonly EvidenceGap[];
  observedAt: string;
  timestamps: Readonly<Record<BusinessDossierModule, string | null>>;
  recordCounts: Readonly<Record<BusinessDossierModule, number>>;
}>): readonly SourceCoverageItem[] => params.moduleReasons.map((reason) => {
  const definition = OFFICIAL_COVERAGE_FAMILIES[reason.module];
  const gapCodes = gapCodesForModule(reason.module, params.gaps);
  const failedToolCount = unavailableToolCount(definition.tools, gapCodes);
  const selected = reason.selectedBy.length > 0 || reason.searched;
  const status: SourceCoverageItem["status"] = !selected
    ? "not_applicable"
    : !reason.searched
      ? "skipped"
      : failedToolCount === definition.tools.length
        ? "unavailable"
        : "checked";
  const coverageLevel: SourceCoverageItem["coverageLevel"] = status === "checked"
    ? failedToolCount > 0 ? "partial" : "full"
    : "none";

  return buildSourceCoverageItem(definition, {
    checkedAt: reason.searched ? params.observedAt : null,
    coverageLevel,
    gapCodes,
    recordCount: params.recordCounts[reason.module],
    reason: buildOfficialCoverageReason(
      reason,
      params.recordCounts[reason.module],
      status,
      coverageLevel,
      failedToolCount,
    ),
    sourceFreshness: params.timestamps[reason.module],
    status,
  });
});

const formatModuleTriggers = (triggers: readonly ModuleReason["selectedBy"][number][]): string => {
  if (triggers.length === 0) return "no selector";
  return triggers.map((trigger) => {
    if (trigger === "default") return "default identity lookup";
    if (trigger === "explicit_module") return "explicit modules input";
    if (trigger === "sector_hint") return "explicit sector hint";
    if (trigger === "inferred_sector") return "ACRA SSIC inference";
    if (trigger === "web_hint") return "supplemental web hint";
    return "analyst rerun";
  }).join(", ");
};

const buildModuleReasons = (params: Readonly<{
  requestedModules: readonly BusinessDossierModule[] | undefined;
  suppliedSectorHints: readonly BusinessSectorHint[];
  explicitSectorHints: readonly BusinessSectorHint[];
  webSectorHints: readonly BusinessSectorHint[];
  analystRerun: boolean;
  inferredSectors: readonly InferredBusinessSector[];
  selectedModules: readonly BusinessDossierModule[];
  searchedModules: readonly BusinessDossierModule[];
  matchedModules: readonly BusinessDossierModule[];
  unmatchedModules: readonly BusinessDossierModule[];
  unsearchedModules: readonly BusinessDossierModule[];
}>): readonly ModuleReason[] => {
  const selectedModuleSet = new Set(params.selectedModules);
  const searchedModuleSet = new Set(params.searchedModules);
  const matchedModuleSet = new Set(params.matchedModules);
  const unmatchedModuleSet = new Set(params.unmatchedModules);
  const unsearchedModuleSet = new Set(params.unsearchedModules);
  const requestedModuleSet = params.requestedModules === undefined ? null : new Set(params.requestedModules);

  return ALL_BUSINESS_DOSSIER_MODULES.map((module) => {
    const suppliedSectorHints = params.suppliedSectorHints.filter((sectorHint) =>
      getBusinessModulesForSector(sectorHint).includes(module),
    );
    const explicitSectorHints = params.explicitSectorHints.filter((sectorHint) =>
      getBusinessModulesForSector(sectorHint).includes(module),
    );
    const webSectorHints = params.webSectorHints.filter((sectorHint) =>
      getBusinessModulesForSector(sectorHint).includes(module),
    );
    const inferredSectors = params.inferredSectors
      .filter((sector) => sector.modules.includes(module))
      .map((sector) => sector.sector);
    const selectedBy: ModuleReason["selectedBy"][number][] = [];
    const guide = sectorGuideForModule(module);

    if (module === "acra" && params.requestedModules === undefined) selectedBy.push("default");
    if (requestedModuleSet?.has(module) === true) selectedBy.push("explicit_module");
    if (explicitSectorHints.length > 0) selectedBy.push("sector_hint");
    if (params.requestedModules === undefined && inferredSectors.length > 0) selectedBy.push("inferred_sector");
    if (webSectorHints.length > 0) selectedBy.push("web_hint");
    if (params.analystRerun && selectedModuleSet.has(module) && module !== "acra") selectedBy.push("analyst_rerun");

    const selected = selectedModuleSet.has(module);
    const searched = searchedModuleSet.has(module);
    const matched = matchedModuleSet.has(module);
    const status: ModuleReason["status"] = matched
      ? "matched"
      : unmatchedModuleSet.has(module)
        ? "unmatched"
        : selected && unsearchedModuleSet.has(module)
          ? "needs_identifier"
          : "skipped";
    const triggerText = formatModuleTriggers(selectedBy);
    const explicitScopeNote = params.requestedModules === undefined || inferredSectors.length === 0 || selected
      ? ""
      : " ACRA SSIC suggested this sector, but explicit modules constrained the dossier scope.";
    const reason = selected
      ? searched
        ? matched
          ? `Selected by ${triggerText}; lookup ran and returned public records.`
          : `Selected by ${triggerText}; lookup ran but returned no matching public records.`
        : `Selected by ${triggerText}; lookup needs ${moduleRequiredIdentifierText(module)} before it can run. Rerun with an explicit sector hint and source-specific identifier.`
      : `Skipped because it was not selected by the default identity path, explicit modules, explicit sector hints, supplemental web hints, analyst reruns, or active inferred-sector scope.${explicitScopeNote} Rerun with an explicit sector hint if this sector applies.`;

    return {
      module,
      status,
      selectedBy,
      searched,
      matched,
      reason,
      ...(suppliedSectorHints.length === 0 ? {} : { sectorHints: suppliedSectorHints }),
      ...(inferredSectors.length === 0 ? {} : { inferredSectors }),
      ...(webSectorHints.length === 0 ? {} : { webSectorHints }),
      ...(guide === undefined ? {} : {
        followUpPrompts: guide.followUpPrompts,
        requiredIdentifiers: guide.requiredIdentifiers,
      }),
    };
  });
};

const buildMatchRationale = (confidence: readonly MatchConfidence[]): readonly Readonly<Record<string, unknown>>[] => {
  return confidence.map((entry) => {
    if (entry.confidence === "exact") {
      return {
        source: entry.source,
        confidence: entry.confidence,
        matchedOn: entry.matchedOn,
        rationale: `Exact identifier match${entry.matchedOn === null ? "" : ` on ${entry.matchedOn}`}.`,
      };
    }
    if (entry.confidence === "name-exact") {
      return {
        source: entry.source,
        confidence: entry.confidence,
        matchedOn: entry.matchedOn,
        rationale: `Exact normalized name match${entry.matchedOn === null ? "" : ` on ${entry.matchedOn}`}.`,
      };
    }
    if (entry.confidence === "name-fuzzy") {
      return {
        source: entry.source,
        confidence: entry.confidence,
        matchedOn: entry.matchedOn,
        rationale: "Bounded fuzzy-name match. Confirm with direct source rows before final decisions.",
      };
    }
    return {
      source: entry.source,
      confidence: entry.confidence,
      matchedOn: entry.matchedOn,
      rationale: "No source rows matched the supplied identifiers or names.",
    };
  });
};

type DossierCoverage = Readonly<{
  selectedModules: readonly BusinessDossierModule[];
  searchedModules: readonly BusinessDossierModule[];
  matchedModules: readonly BusinessDossierModule[];
  unmatchedModules: readonly BusinessDossierModule[];
  unsearchedModules: readonly BusinessDossierModule[];
}>;

const confidenceRank = (value: MatchConfidence["confidence"]): number => {
  if (value === "exact") return 1;
  if (value === "name-exact") return 0.8;
  if (value === "name-fuzzy") return 0.5;
  return 0;
};

const confidenceLevel = (score: number): "high" | "medium" | "low" =>
  score >= 0.8 ? "high" : score >= 0.5 ? "medium" : "low";

const roundScore = (score: number): number => Math.round(score * 100) / 100;

const compareIdentitySignals = (a: MatchConfidence, b: MatchConfidence): number => {
  const sourcePriority = (source: string): number => source === "ACRA" ? 1 : 0;
  const scoreDelta = confidenceRank(b.confidence) - confidenceRank(a.confidence);
  if (scoreDelta !== 0) return scoreDelta;
  return sourcePriority(b.source) - sourcePriority(a.source);
};

const resolveDossierConfidence = (
  confidence: readonly MatchConfidence[],
  coverage: DossierCoverage,
): Readonly<Record<string, unknown>> => {
  if (confidence.length === 0) {
    return {
      level: "low",
      score: 0,
      rationale: "No confidence signals were generated because no searchable module had qualifying input.",
      identity: {
        level: "low",
        score: 0,
        primarySource: null,
        matchedOn: null,
        rationale: "No searchable identity source returned a match signal.",
      },
      coverage: {
        selectedModules: coverage.selectedModules,
        searchedModules: coverage.searchedModules,
        matchedModules: coverage.matchedModules,
        unmatchedModules: coverage.unmatchedModules,
        unsearchedModules: coverage.unsearchedModules,
        score: 0,
        rationale: "No selected modules were searched because the supplied identifiers did not qualify for any lookup.",
      },
    };
  }

  const identitySignals = confidence
    .filter((entry) => entry.source === "ACRA" || entry.confidence === "exact")
    .sort(compareIdentitySignals);
  const bestIdentitySignal = identitySignals[0] ?? [...confidence].sort(compareIdentitySignals)[0];
  const identityScore = bestIdentitySignal === undefined ? 0 : confidenceRank(bestIdentitySignal.confidence);
  const roundedIdentityScore = roundScore(identityScore);
  const identityLevel = confidenceLevel(roundedIdentityScore);
  const searchedCount = coverage.searchedModules.length;
  const coverageScore = searchedCount === 0 ? 0 : coverage.matchedModules.length / searchedCount;
  const roundedCoverageScore = roundScore(coverageScore);

  return {
    level: identityLevel,
    score: roundedIdentityScore,
    rationale: identityLevel === "high"
      ? `Identity confidence is high from ${bestIdentitySignal?.source ?? "the strongest source"}; coverage breadth is tracked separately.`
      : identityLevel === "medium"
        ? "Identity confidence is based on bounded name matching; coverage breadth is tracked separately."
        : "Identity confidence is weak or missing across searched modules; coverage breadth is tracked separately.",
    identity: {
      level: identityLevel,
      score: roundedIdentityScore,
      primarySource: bestIdentitySignal?.source ?? null,
      matchedOn: bestIdentitySignal?.matchedOn ?? null,
      rationale: bestIdentitySignal === undefined || bestIdentitySignal.confidence === "no-match"
        ? "No official identity source returned a match."
        : `${bestIdentitySignal.source} returned a ${bestIdentitySignal.confidence} match${bestIdentitySignal.matchedOn === null ? "" : ` on ${bestIdentitySignal.matchedOn}`}.`,
    },
    coverage: {
      selectedModules: coverage.selectedModules,
      searchedModules: coverage.searchedModules,
      matchedModules: coverage.matchedModules,
      unmatchedModules: coverage.unmatchedModules,
      unsearchedModules: coverage.unsearchedModules,
      score: roundedCoverageScore,
      rationale: `${coverage.matchedModules.length} of ${searchedCount} searched modules returned evidence; ${coverage.unsearchedModules.length} selected modules were not searchable from the supplied input.`,
    },
  };
};

const hasCredentialGap = (gapCodes: readonly string[]): boolean =>
  gapCodes.some((code) => /API_KEY_REQUIRED|API_TOKEN_REQUIRED|TOKEN_REQUIRED|CREDENTIAL/i.test(code));

const hasUnavailableGap = (gapCodes: readonly string[]): boolean =>
  gapCodes.some((code) => /UNAVAILABLE|UPSTREAM_FAILED|FAILED|TIMEOUT|RATE_LIMIT|HTTP/i.test(code));

const supplementalNoRecordReason = (label: string): string => {
  if (/sanctions/i.test(label)) {
    return "OpenSanctions screening ran and returned no candidate matches above threshold; this is not a sanctions clearance or AML determination.";
  }
  if (/opencorporates/i.test(label)) {
    return "OpenCorporates search ran and returned no candidate company links; this is a cross-link gap, not an ownership or control conclusion.";
  }
  if (/adverse/i.test(label)) {
    return "Adverse-media lite ran against bounded official feeds and returned no keyword matches; this is not open-web adverse-media clearance.";
  }
  if (/relationship/i.test(label)) {
    return "Relationship graph construction ran on supplied dossier records; absent graph edges are not proof that no relationship exists.";
  }
  return "Source check ran and returned no public records; absence of returned evidence is a gap, not a clearance claim.";
};

const buildSupplementalCoverageReason = (
  definition: CoverageFamilyDefinition,
  status: SourceCoverageItem["status"],
  coverageLevel: SourceCoverageItem["coverageLevel"],
  recordCount: number,
  gapCodes: readonly string[],
): string => {
  if (status === "credential_blocked") {
    return `${definition.label} was not checked because required credentials are not configured. Treat this as a confidence blocker.`;
  }
  if (status === "unavailable") {
    return `${definition.label} was attempted but the upstream source was unavailable or failed. Treat this as a coverage gap.`;
  }
  if (coverageLevel === "partial") {
    return `${definition.label} ran with partial provider/feed coverage; returned ${recordCount} record(s), with unresolved gaps: ${gapCodes.join(", ")}.`;
  }
  if (recordCount === 0) {
    return supplementalNoRecordReason(definition.label);
  }
  return `${definition.label} ran and returned ${recordCount} analyst-review record(s).`;
};

const buildSupplementalCoverageItems = (params: Readonly<{
  includeExternalDiligence: boolean | undefined;
  externalName: string | undefined;
  externalArtifacts: readonly BriefArtifact[];
  observedAt: string;
}>): readonly SourceCoverageItem[] => {
  const artifactByTitle = new Map(params.externalArtifacts.map((artifact) => [artifact.title, artifact]));

  return SUPPLEMENTAL_COVERAGE_FAMILIES.map(({ artifactTitle, definition }) => {
    if (params.includeExternalDiligence !== true) {
      return buildSourceCoverageItem(definition, {
        checkedAt: null,
        coverageLevel: "none",
        recordCount: 0,
        reason: "Supplemental CDD was not requested for this compatibility dossier run. Run the CDD orchestrator or set includeExternalDiligence to check this source family.",
        status: "skipped",
      });
    }
    if (params.externalName === undefined) {
      return buildSourceCoverageItem(definition, {
        checkedAt: null,
        coverageLevel: "none",
        recordCount: 0,
        reason: "No resolved entity name or UEN was available for this supplemental source query.",
        status: "skipped",
      });
    }

    const artifact = artifactByTitle.get(artifactTitle);
    if (artifact === undefined) {
      return buildSourceCoverageItem(definition, {
        checkedAt: null,
        coverageLevel: "none",
        recordCount: 0,
        reason: "This supplemental source did not run in the current dossier build.",
        status: "skipped",
      });
    }

    const gapCodes = artifact.gaps.map((gap) => gap.code);
    const recordCount = artifact.provenance.reduce((count, item) => count + item.recordCount, 0);
    const credentialBlocked = hasCredentialGap(gapCodes);
    const unavailable = !credentialBlocked && hasUnavailableGap(gapCodes) && artifact.provenance.length === 0;
    const partial = !credentialBlocked && !unavailable && hasUnavailableGap(gapCodes) && artifact.provenance.length > 0;
    const status: SourceCoverageItem["status"] = credentialBlocked
      ? "credential_blocked"
      : unavailable
        ? "unavailable"
        : "checked";
    const coverageLevel: SourceCoverageItem["coverageLevel"] = status === "checked"
      ? partial ? "partial" : "full"
      : "none";

    return buildSourceCoverageItem(definition, {
      checkedAt: status === "checked" ? params.observedAt : null,
      coverageLevel,
      gapCodes,
      recordCount,
      reason: buildSupplementalCoverageReason(definition, status, coverageLevel, recordCount, gapCodes),
      sourceFreshness: artifact.freshness[0]?.upstreamTimestamp ?? null,
      status,
    });
  });
};

const buildOrchestratorOnlyCoverageItems = (): readonly SourceCoverageItem[] =>
  ORCHESTRATOR_ONLY_COVERAGE_FAMILIES.map((definition) =>
    buildSourceCoverageItem(definition, {
      checkedAt: null,
      coverageLevel: "none",
      recordCount: 0,
      reason: `${definition.label} is collected by the CDD orchestrator and was not run by the low-level sg_business_dossier compatibility path.`,
      sourceFreshness: null,
      status: "skipped",
    }));

const buildDossierHandoffMarkdown = (params: BusinessDossierParams, data: {
  readonly selectedModules: readonly BusinessDossierModule[];
  readonly searchedModules: readonly BusinessDossierModule[];
  readonly matchedModules: readonly BusinessDossierModule[];
  readonly unmatchedModules: readonly BusinessDossierModule[];
  readonly riskFlags: readonly RiskFlag[];
  readonly analystFollowUps: readonly AnalystFollowUp[];
}): string => {
  const lines = [
    "## Due Diligence Handoff",
    "",
    `Entity input: ${params.entityName ?? params.uen ?? params.registrationNo ?? "unspecified"}`,
    `Modules selected: ${data.selectedModules.join(", ") || "none"}`,
    `Modules searched: ${data.searchedModules.join(", ") || "none"}`,
    `Modules matched: ${data.matchedModules.join(", ") || "none"}`,
    `Modules unmatched: ${data.unmatchedModules.join(", ") || "none"}`,
    "",
    "### Risk Flags",
  ];

  if (data.riskFlags.length === 0) {
    lines.push("- none");
  } else {
    for (const flag of data.riskFlags) {
      lines.push(`- [${flag.severity}] ${flag.code} (${flag.source}): ${flag.message}`);
    }
  }

  lines.push("");
  lines.push("### Prioritized Analyst Follow-ups");
  if (data.analystFollowUps.length === 0) {
    lines.push("- none");
  } else {
    data.analystFollowUps.forEach((followUp, index) => {
      lines.push(`${index + 1}. [${followUp.priority}/${followUp.category}] ${followUp.action}`);
      lines.push(`   - Evidence gap: ${followUp.reason}`);
      lines.push(`   - Why this matters: ${followUp.whyThisMatters}`);
    });
  }

  return lines.join("\n");
};

export const buildBusinessDossierArtifact = async (
  params: BusinessDossierParams,
): Promise<BriefArtifact> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const suppliedSectorHints = params.sectorHints ?? [];
  const explicitSectorHints = params.explicitSectorHints ?? suppliedSectorHints;
  const webSectorHints = params.webSectorHints ?? [];
  const initialSelectedModules = selectBusinessDossierModules(params.modules, suppliedSectorHints);
  const initialSelectedModuleSet = new Set<BusinessDossierModule>(initialSelectedModules);
  const searchedModules = new Set<BusinessDossierModule>();
  const matchedModules = new Set<BusinessDossierModule>();

  const shouldSearchAcra = initialSelectedModuleSet.has("acra") && (params.entityName !== undefined || params.uen !== undefined);
  if (shouldSearchAcra) searchedModules.add("acra");

  const acraRecords = shouldSearchAcra
    ? await safeRead(
        "ACRA_UNAVAILABLE",
        "ACRA lookup failed",
        () => getAcraEntities({ entityName: params.entityName, uen: params.uen, limit: 5 }),
        gaps,
      )
    : null;
  const acra = acraRecords ?? [];
  const resolvedEntityName = params.entityName
    ?? (typeof acra[0]?.entityName === "string" ? acra[0].entityName : undefined);
  const searchParams: BusinessDossierParams = { ...params, entityName: resolvedEntityName };
  const inferredSectors = inferBusinessSectorsFromAcra(acra);
  const inferredSectorHints = inferredSectors.map((sector) => sector.sector);
  const effectiveSectorHints = params.modules === undefined
    ? Array.from(new Set<BusinessSectorHint>([...suppliedSectorHints, ...inferredSectorHints]))
    : suppliedSectorHints;
  const selectedModules = selectBusinessDossierModules(params.modules, effectiveSectorHints);
  const selectedModuleSet = new Set<BusinessDossierModule>(selectedModules);
  const hasCeaSpecificInput = searchParams.salespersonName !== undefined
    || searchParams.registrationNo !== undefined
    || searchParams.estateAgentName !== undefined
    || searchParams.estateAgentLicenseNo !== undefined;
  const effectiveEstateAgentName = searchParams.estateAgentName
    ?? (selectedModuleSet.has("cea") && !hasCeaSpecificInput ? searchParams.entityName : undefined);

  const shouldSearchBca = selectedModuleSet.has("bca")
    && (searchParams.entityName !== undefined || searchParams.uen !== undefined || searchParams.classCode !== undefined || searchParams.workhead !== undefined || searchParams.grade !== undefined);
  const shouldSearchCea = selectedModuleSet.has("cea")
    && (
      searchParams.salespersonName !== undefined
      || searchParams.registrationNo !== undefined
      || effectiveEstateAgentName !== undefined
      || searchParams.estateAgentLicenseNo !== undefined
    );
  const shouldSearchGebiz = selectedModuleSet.has("gebiz") && searchParams.entityName !== undefined;
  const shouldSearchBoa = selectedModuleSet.has("boa") && (searchParams.entityName !== undefined || searchParams.registrationNo !== undefined);
  const shouldSearchHsa = selectedModuleSet.has("hsa") && searchParams.entityName !== undefined;
  const shouldSearchHlb = selectedModuleSet.has("hlb") && searchParams.entityName !== undefined;

  if (shouldSearchBca) searchedModules.add("bca");
  if (shouldSearchCea) searchedModules.add("cea");
  if (shouldSearchGebiz) searchedModules.add("gebiz");
  if (shouldSearchBoa) searchedModules.add("boa");
  if (shouldSearchHsa) searchedModules.add("hsa");
  if (shouldSearchHlb) searchedModules.add("hlb");

  const shouldSearchByModule = {
    acra: shouldSearchAcra,
    bca: shouldSearchBca,
    boa: shouldSearchBoa,
    cea: shouldSearchCea,
    gebiz: shouldSearchGebiz,
    hlb: shouldSearchHlb,
    hsa: shouldSearchHsa,
  } satisfies Readonly<Record<BusinessDossierModule, boolean>>;

  for (const module of selectedModules) {
    if (!shouldSearchByModule[module]) {
      gaps.push(buildNeedsIdentifierGap(module));
    }
  }

  const [
    bcaLicensedBuilders,
    bcaRegisteredContractors,
    ceaSalespersons,
    gebizTenders,
    boaArchitects,
    boaArchitectureFirms,
    hsaLicensedPharmacies,
    hsaHealthProductLicensees,
    hlbHotels,
  ] = await Promise.all([
    shouldSearchBca
      ? safeRead(
          "BCA_BUILDERS_UNAVAILABLE",
          "BCA licensed-builder lookup failed",
          () => getBcaLicensedBuilders({
            companyName: searchParams.entityName,
            uenNo: searchParams.uen,
            classCode: searchParams.classCode,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchBca
      ? safeRead(
          "BCA_CONTRACTORS_UNAVAILABLE",
          "BCA registered-contractor lookup failed",
          () => getBcaRegisteredContractors({
            companyName: searchParams.entityName,
            uenNo: searchParams.uen,
            workhead: searchParams.workhead,
            grade: searchParams.grade,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchCea
      ? safeRead(
          "CEA_UNAVAILABLE",
          "CEA lookup failed",
          () => getCeaSalespersons({
            salespersonName: searchParams.salespersonName,
            registrationNo: searchParams.registrationNo,
            estateAgentName: effectiveEstateAgentName,
            estateAgentLicenseNo: searchParams.estateAgentLicenseNo,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchGebiz
      ? safeRead(
          "GEBIZ_UNAVAILABLE",
          "GeBIZ lookup failed",
          () => getGeBIZTenders({ supplierName: searchParams.entityName, limit: 10 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchBoa
      ? safeRead(
          "BOA_ARCHITECTS_UNAVAILABLE",
          "BOA architects lookup failed",
          async () => {
            if (searchParams.registrationNo !== undefined) {
              return getBoaArchitects({ registrationNo: searchParams.registrationNo, limit: 5 });
            }
            const byFirm = await getBoaArchitects({ firmName: searchParams.entityName, limit: 5 });
            return byFirm.length > 0 || searchParams.entityName === undefined
              ? byFirm
              : getBoaArchitects({ name: searchParams.entityName, limit: 5 });
          },
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchBoa
      ? safeRead(
          "BOA_FIRMS_UNAVAILABLE",
          "BOA architecture-firm lookup failed",
          () => getBoaArchitectureFirms({ firmName: searchParams.entityName, limit: 5 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchHsa
      ? safeRead(
          "HSA_PHARMACIES_UNAVAILABLE",
          "HSA pharmacy lookup failed",
          () => getHsaLicensedPharmacies({ pharmacyName: searchParams.entityName, limit: 5 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchHsa
      ? safeRead(
          "HSA_LICENSEES_UNAVAILABLE",
          "HSA health-product licensee lookup failed",
          () => getHsaHealthProductLicensees({ companyName: searchParams.entityName, limit: 10 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchHlb
      ? safeRead(
          "HLB_UNAVAILABLE",
          "HLB hotel lookup failed",
          async () => {
            const byKeeper = await getHlbHotels({ keeperName: searchParams.entityName, limit: 5 });
            return byKeeper.length > 0 || searchParams.entityName === undefined
              ? byKeeper
              : getHlbHotels({ name: searchParams.entityName, limit: 5 });
          },
          gaps,
        )
      : Promise.resolve(null),
  ]);

  const builders = bcaLicensedBuilders ?? [];
  const contractors = bcaRegisteredContractors ?? [];
  const salespersons = ceaSalespersons ?? [];
  const tenders = gebizTenders ?? [];
  const architects = boaArchitects ?? [];
  const architectureFirms = boaArchitectureFirms ?? [];
  const pharmacies = hsaLicensedPharmacies ?? [];
  const licensees = hsaHealthProductLicensees ?? [];
  const hotels = hlbHotels ?? [];

  if (acra.length > 0) matchedModules.add("acra");
  if (builders.length > 0 || contractors.length > 0) matchedModules.add("bca");
  if (salespersons.length > 0) matchedModules.add("cea");
  if (tenders.length > 0) matchedModules.add("gebiz");
  if (architects.length > 0 || architectureFirms.length > 0) matchedModules.add("boa");
  if (pharmacies.length > 0 || licensees.length > 0) matchedModules.add("hsa");
  if (hotels.length > 0) matchedModules.add("hlb");

  if (shouldSearchAcra && acra.length === 0) {
    gaps.push(toGap("ACRA_NO_MATCH", "No exact ACRA entity matched the provided company name or UEN."));
  }
  if (shouldSearchBca && builders.length === 0) {
    gaps.push(toGap("BCA_BUILDERS_NO_MATCH", "No licensed-builder record matched the provided company, UEN, or class code."));
  }
  if (shouldSearchBca && contractors.length === 0) {
    gaps.push(toGap("BCA_CONTRACTORS_NO_MATCH", "No registered-contractor record matched the provided company, UEN, workhead, or grade."));
  }
  if (shouldSearchCea && salespersons.length === 0) {
    gaps.push(toGap("CEA_NO_MATCH", "No CEA salesperson or estate-agent record matched the provided identifier."));
  }
  if (shouldSearchGebiz && tenders.length === 0) {
    gaps.push(toGap("GEBIZ_NO_MATCH", "No GeBIZ supplier award rows matched the provided entity name."));
  }
  if (shouldSearchBoa && architects.length === 0 && architectureFirms.length === 0) {
    gaps.push(toGap("BOA_NO_MATCH", "No BOA architect or architecture-firm record matched the provided identifier."));
  }
  if (shouldSearchHsa && pharmacies.length === 0 && licensees.length === 0) {
    gaps.push(toGap("HSA_NO_MATCH", "No HSA pharmacy or health-product licence row matched the provided entity name."));
  }
  if (shouldSearchHlb && hotels.length === 0) {
    gaps.push(toGap("HLB_NO_MATCH", "No HLB hotel record matched the provided hotel or keeper name."));
  }

  const unmatchedModules = selectedModules.filter((module) => searchedModules.has(module) && !matchedModules.has(module));
  const unsearchedModules = selectedModules.filter((module) => !searchedModules.has(module));
  const searchedModuleList = Array.from(searchedModules);
  const matchedModuleList = Array.from(matchedModules);
  const moduleReasons = buildModuleReasons({
    analystRerun: params.analystRerun === true,
    explicitSectorHints,
    requestedModules: params.modules,
    suppliedSectorHints,
    webSectorHints,
    inferredSectors,
    selectedModules,
    searchedModules: searchedModuleList,
    matchedModules: matchedModuleList,
    unmatchedModules,
    unsearchedModules,
  });

  const matchConfidence: MatchConfidence[] = [
    ...(shouldSearchAcra
      ? [resolveEntityMatchConfidence("ACRA", acra, {
          exactInputs: params.uen === undefined ? [] : [{ value: params.uen, fields: ["uen"] }],
          nameInputs: params.entityName === undefined ? [] : [{ value: params.entityName, fields: ["entityName"] }],
        })]
      : []),
    ...(shouldSearchBca
      ? [
          resolveEntityMatchConfidence("BCA licensed builders", builders, {
            exactInputs: searchParams.uen === undefined ? [] : [{ value: searchParams.uen, fields: ["uenNo"] }],
            nameInputs: searchParams.entityName === undefined ? [] : [{ value: searchParams.entityName, fields: ["companyName"] }],
          }),
          resolveEntityMatchConfidence("BCA registered contractors", contractors, {
            exactInputs: searchParams.uen === undefined ? [] : [{ value: searchParams.uen, fields: ["uenNo"] }],
            nameInputs: searchParams.entityName === undefined ? [] : [{ value: searchParams.entityName, fields: ["companyName"] }],
          }),
        ]
      : []),
    ...(shouldSearchCea
      ? [resolveEntityMatchConfidence("CEA", salespersons, {
          exactInputs: [
            ...(params.registrationNo === undefined ? [] : [{ value: params.registrationNo, fields: ["registrationNo"] }]),
            ...(params.estateAgentLicenseNo === undefined ? [] : [{ value: params.estateAgentLicenseNo, fields: ["estateAgentLicenseNo"] }]),
          ],
          nameInputs: [
            ...(params.salespersonName === undefined ? [] : [{ value: params.salespersonName, fields: ["salespersonName"] }]),
            ...(effectiveEstateAgentName === undefined ? [] : [{ value: effectiveEstateAgentName, fields: ["estateAgentName"] }]),
          ],
        })]
      : []),
    ...(shouldSearchGebiz
      ? [resolveEntityMatchConfidence("GeBIZ", tenders as readonly Readonly<Record<string, unknown>>[], {
          nameInputs: searchParams.entityName === undefined ? [] : [{ value: searchParams.entityName, fields: ["supplierName"] }],
        })]
      : []),
    ...(shouldSearchBoa
      ? [
          resolveEntityMatchConfidence("BOA architects", architects as readonly Readonly<Record<string, unknown>>[], {
            exactInputs: searchParams.registrationNo === undefined ? [] : [{ value: searchParams.registrationNo, fields: ["registrationNo"] }],
            nameInputs: searchParams.entityName === undefined ? [] : [
              { value: searchParams.entityName, fields: ["architectName"] },
              { value: searchParams.entityName, fields: ["firmName"] },
            ],
          }),
          resolveEntityMatchConfidence("BOA architecture firms", architectureFirms as readonly Readonly<Record<string, unknown>>[], {
            nameInputs: searchParams.entityName === undefined ? [] : [{ value: searchParams.entityName, fields: ["firmName"] }],
          }),
        ]
      : []),
    ...(shouldSearchHsa
      ? [
          resolveEntityMatchConfidence("HSA licensed pharmacies", pharmacies as readonly Readonly<Record<string, unknown>>[], {
            nameInputs: searchParams.entityName === undefined ? [] : [{ value: searchParams.entityName, fields: ["pharmacyName"] }],
          }),
          resolveEntityMatchConfidence("HSA health product licensees", licensees as readonly Readonly<Record<string, unknown>>[], {
            nameInputs: searchParams.entityName === undefined ? [] : [{ value: searchParams.entityName, fields: ["companyName"] }],
          }),
        ]
      : []),
    ...(shouldSearchHlb
      ? [resolveEntityMatchConfidence("HLB hotels", hotels as readonly Readonly<Record<string, unknown>>[], {
          nameInputs: searchParams.entityName === undefined ? [] : [
            { value: searchParams.entityName, fields: ["name"] },
            { value: searchParams.entityName, fields: ["keeperName"] },
          ],
        })]
      : []),
  ];

  const primaryAcra = acra[0];
  const primaryBuilder = builders[0];
  const primaryContractor = contractors[0];
  const primarySalesperson = salespersons[0];
  const primaryArchitect = architects[0];
  const primaryArchitectureFirm = architectureFirms[0];
  const primaryPharmacy = pharmacies[0];
  const primaryLicensee = licensees[0];
  const primaryHotel = hotels[0];
  const primaryTender = tenders[0];
  const riskFlags = [
    ...buildBusinessRiskFlags(searchParams, searchedModules, acra, builders, contractors, licensees),
    ...(searchedModules.size > 0 && matchedModules.size === 0
      ? [{
          code: "NO_MODULE_MATCHES",
          severity: "high" as const,
          message: "No selected module produced matched evidence for the supplied identifiers.",
          source: "Resolver",
        }]
      : []),
    ...(matchedModules.size > 0 && unmatchedModules.length > 0
      ? [{
          code: "PARTIAL_MODULE_COVERAGE",
          severity: "medium" as const,
          message: `Matched ${matchedModules.size} of ${searchedModules.size} searched modules; unmatched modules require follow-up.`,
          source: "Resolver",
        }]
      : []),
  ] satisfies readonly RiskFlag[];
  const matchRationale = buildMatchRationale(matchConfidence);
  const dossierConfidence = resolveDossierConfidence(matchConfidence, {
    selectedModules,
    searchedModules: searchedModuleList,
    matchedModules: matchedModuleList,
    unmatchedModules,
    unsearchedModules,
  });
  const nextChecks = buildBusinessNextChecks(searchParams, selectedModules);
  const externalQueryName = primaryAcra?.entityName ?? searchParams.entityName;
  const externalUen = primaryAcra?.uen ?? params.uen;
  const externalName = externalQueryName ?? externalUen;
  const externalArtifacts = params.includeExternalDiligence === true && externalName !== undefined
    ? await Promise.all([
        buildSanctionsScreenArtifact({ name: externalName, ...(externalUen === undefined ? {} : { uen: externalUen }) }),
        buildOpenCorporatesLinksArtifact({ entityName: externalName, ...(externalUen === undefined ? {} : { uen: externalUen }), jurisdictionCode: "sg" }),
        buildAdverseMediaLiteArtifact({ keyword: externalName }),
        buildRelationshipGraphArtifact({
          records: {
            acra,
            bcaLicensedBuilders: builders,
            bcaRegisteredContractors: contractors,
            ceaSalespersons: salespersons,
            gebizTenders: tenders,
            boaArchitects: architects,
            boaArchitectureFirms: architectureFirms,
            hsaLicensedPharmacies: pharmacies,
            hsaHealthProductLicensees: licensees,
            hlbHotels: hotels,
          },
        }),
      ])
    : [];
  const externalEvidence = externalArtifacts.flatMap((artifact) =>
    artifact.evidence.map((item) => ({
      ...item,
      label: `${artifact.title}: ${item.label}`,
    })),
  );
  const externalRecords = externalArtifacts.map((artifact) => ({
    title: artifact.title,
    summary: artifact.summary,
    records: artifact.records,
    gaps: artifact.gaps,
    provenance: artifact.provenance,
    freshness: artifact.freshness,
    limits: artifact.limits,
    riskFlags: artifact.riskFlags ?? [],
  }));
  const officialCoverage = buildOfficialCoverageItems({
    gaps,
    moduleReasons,
    observedAt,
    recordCounts: {
      acra: acra.length,
      bca: coverageRecordCount([builders, contractors]),
      boa: coverageRecordCount([architects, architectureFirms]),
      cea: salespersons.length,
      gebiz: tenders.length,
      hlb: hotels.length,
      hsa: coverageRecordCount([pharmacies, licensees]),
    },
    timestamps: {
      acra: getFirstTimestamp(acra, ["annualReturnDate", "accountDueDate", "registrationIncorporationDate"]),
      bca: getFirstTimestamp([...builders, ...contractors], ["expiryDate"]),
      boa: null,
      cea: getFirstTimestamp(salespersons, ["registrationEndDate", "registrationStartDate"]),
      gebiz: getFirstTimestamp(tenders as readonly Readonly<Record<string, unknown>>[], ["awardDate"]),
      hlb: getFirstTimestamp(hotels as readonly Readonly<Record<string, unknown>>[], ["lastUpdatedAt"]),
      hsa: getFirstTimestamp(licensees as readonly Readonly<Record<string, unknown>>[], ["expiryDate"]),
    },
  });
  const sourceCoverage = [
    ...officialCoverage,
    ...buildSupplementalCoverageItems({
      externalArtifacts,
      externalName,
      includeExternalDiligence: params.includeExternalDiligence,
      observedAt,
    }),
    ...buildOrchestratorOnlyCoverageItems(),
  ];
  const finalGaps = [
    ...gaps,
    ...externalArtifacts.flatMap((artifact) => artifact.gaps),
  ];
  const finalLimits = [
    ...buildBusinessLimits(selectedModules),
    ...externalArtifacts.flatMap((artifact) => artifact.limits),
  ];
  const finalRiskFlags = [
    ...riskFlags,
    ...externalArtifacts.flatMap((artifact) => artifact.riskFlags ?? []),
  ];
  const analystFollowUps = buildDossierAnalystFollowUps({
    gaps: finalGaps,
    limits: finalLimits,
    matchConfidence,
    nextChecks,
    sourceCoverage,
  });
  const handoffMarkdown = buildDossierHandoffMarkdown(params, {
    selectedModules,
    searchedModules: searchedModuleList,
    matchedModules: matchedModuleList,
    unmatchedModules,
    riskFlags: finalRiskFlags,
    analystFollowUps,
  });

  const artifact: BriefArtifact = {
    title: "Business Dossier",
    summary: [
      { label: "Entity", value: primaryAcra?.entityName ?? primaryArchitectureFirm?.firmName ?? primaryLicensee?.companyName ?? params.entityName ?? null, source: primaryAcra !== undefined ? "ACRA" : primaryArchitectureFirm !== undefined ? "BOA" : primaryLicensee !== undefined ? "HSA" : "Requested" },
      { label: "UEN", value: primaryAcra?.uen ?? params.uen ?? null, source: "ACRA" },
      { label: "Entity status", value: primaryAcra?.entityStatusDescription ?? null, source: "ACRA" },
      { label: "Licensed builder", value: primaryBuilder?.classCode ?? null, source: "BCA" },
      { label: "Registered contractor", value: primaryContractor?.workhead ?? null, source: "BCA" },
      { label: "Estate agent", value: primarySalesperson?.estateAgentName ?? params.estateAgentName ?? null, source: "CEA" },
      { label: "Architecture firm", value: primaryArchitectureFirm?.firmName ?? primaryArchitect?.firmName ?? null, source: "BOA" },
      { label: "Health-product licence", value: primaryLicensee?.licenseType ?? null, source: "HSA" },
      { label: "Licensed pharmacy", value: primaryPharmacy?.pharmacyName ?? null, source: "HSA" },
      { label: "Hotel keeper", value: primaryHotel?.keeperName ?? null, source: "HLB" },
    ],
    evidence: [
      { label: "Selected modules", value: selectedModules.length, source: "Resolver" },
      { label: "Searched modules", value: searchedModules.size, source: "Resolver" },
      { label: "Matched modules", value: matchedModules.size, source: "Resolver" },
      { label: "Unsearched modules", value: unsearchedModules.length, source: "Resolver" },
      { label: "Inferred sectors", value: inferredSectors.length, source: "Resolver" },
      { label: "ACRA matches", value: acra.length, source: "ACRA" },
      { label: "BCA licensed-builder matches", value: builders.length, source: "BCA" },
      { label: "BCA contractor matches", value: contractors.length, source: "BCA" },
      { label: "CEA matches", value: salespersons.length, source: "CEA" },
      { label: "GeBIZ award matches", value: tenders.length, source: "GeBIZ" },
      { label: "BOA architect matches", value: architects.length, source: "BOA" },
      { label: "BOA firm matches", value: architectureFirms.length, source: "BOA" },
      { label: "HSA pharmacy matches", value: pharmacies.length, source: "HSA" },
      { label: "HSA health-product matches", value: licensees.length, source: "HSA" },
      { label: "HLB hotel matches", value: hotels.length, source: "HLB" },
      { label: "Officer count", value: primaryAcra?.noOfOfficers ?? null, source: "ACRA" },
      { label: "Builder expiry", value: primaryBuilder?.expiryDate ?? null, source: "BCA" },
      { label: "Hotel rooms", value: primaryHotel?.totalRooms ?? null, source: "HLB" },
      { label: "Top GeBIZ tender", value: primaryTender?.tenderNo ?? null, source: "GeBIZ" },
      ...externalEvidence,
    ],
    records: {
      resolution: {
        requestedEntityName: params.entityName ?? null,
        requestedUen: params.uen ?? null,
        requestedSalespersonName: params.salespersonName ?? null,
        requestedRegistrationNo: params.registrationNo ?? null,
        selectedModules,
        sectorHints: params.sectorHints ?? [],
        explicitSectorHints,
        webSectorHints,
        analystRerun: params.analystRerun === true,
        effectiveSectorHints,
        inferredSectors,
        searchedModules: searchedModuleList,
        matchedModules: matchedModuleList,
        unmatchedModules,
        unsearchedModules,
        moduleReasons,
        sectorWorkflowGuide: SECTOR_WORKFLOW_GUIDE,
        sectorSelectionContext: {
          explicitSectorHints,
          acraSsicInferredSectorHints: inferredSectorHints,
          webSectorHints,
          analystRerun: params.analystRerun === true,
          reversible: "Sector inference is bounded; rerun with explicit sectorHints and source-specific identifiers to change the module set.",
        },
      },
      quality: {
        dossierConfidence,
        matchRationale,
        riskRules: {
          schemaVersion: SG_RISK_RULES_SCHEMA_VERSION,
          version: SG_RISK_RULES_VERSION,
          source: SG_RISK_RULES_SOURCE,
          lastReviewed: SG_RISK_RULES_LAST_REVIEWED,
        },
      },
      handoff: {
        markdown: handoffMarkdown,
      },
      acra,
      bcaLicensedBuilders: builders,
      bcaRegisteredContractors: contractors,
      ceaSalespersons: salespersons,
      gebizTenders: tenders,
      boaArchitects: architects,
      boaArchitectureFirms: architectureFirms,
      hsaLicensedPharmacies: pharmacies,
      hsaHealthProductLicensees: licensees,
      hlbHotels: hotels,
      externalDiligence: externalRecords,
    },
    gaps: finalGaps,
    provenance: [
      ...(searchedModules.has("acra")
        ? [toProvenance("ACRA", "sg_acra_entities", "Exact-match company and UEN registry evidence.", false, acra.length)]
        : []),
      ...(searchedModules.has("bca")
        ? [
            toProvenance("BCA", "sg_bca_licensed_builders", "Licensed-builder registry evidence for the named entity or class code.", false, builders.length),
            toProvenance("BCA", "sg_bca_registered_contractors", "Registered-contractor registry evidence for the named entity, workhead, or grade.", false, contractors.length),
          ]
        : []),
      ...(searchedModules.has("cea")
        ? [toProvenance("CEA", "sg_cea_salespersons", "Salesperson and estate-agent registry evidence for the supplied identifiers.", false, salespersons.length)]
        : []),
      ...(searchedModules.has("gebiz")
        ? [toProvenance("GeBIZ", "sg_gebiz_tenders", "Government procurement award history for the named supplier.", false, tenders.length)]
        : []),
      ...(searchedModules.has("boa")
        ? [
            toProvenance("BOA", "sg_boa_architects", "Board of Architects architect registry evidence for the supplied firm or registration identifier.", false, architects.length),
            toProvenance("BOA", "sg_boa_architecture_firms", "Board of Architects architecture-firm registry evidence for the supplied firm identifier.", false, architectureFirms.length),
          ]
        : []),
      ...(searchedModules.has("hsa")
        ? [
            toProvenance("HSA", "sg_hsa_licensed_pharmacies", "Licensed pharmacy evidence for the named entity.", false, pharmacies.length),
            toProvenance("HSA", "sg_hsa_health_product_licensees", "Health-product licensing evidence for the named company.", false, licensees.length),
          ]
        : []),
      ...(searchedModules.has("hlb")
        ? [toProvenance("HLB", "sg_hlb_hotels", "Hotels Licensing Board hotel and keeper evidence for the named entity.", false, hotels.length)]
        : []),
      ...externalArtifacts.flatMap((artifact) => artifact.provenance),
    ],
    freshness: [
      ...(searchedModules.has("acra")
        ? [toFreshness("ACRA", observedAt, getFirstTimestamp(acra, ["annualReturnDate", "accountDueDate", "registrationIncorporationDate"]))]
        : []),
      ...(searchedModules.has("bca")
        ? [
            toFreshness("BCA licensed builders", observedAt, getFirstTimestamp(builders, ["expiryDate"])),
            toFreshness("BCA registered contractors", observedAt, getFirstTimestamp(contractors, ["expiryDate"])),
          ]
        : []),
      ...(searchedModules.has("cea")
        ? [toFreshness("CEA", observedAt, getFirstTimestamp(salespersons, ["registrationEndDate", "registrationStartDate"]))]
        : []),
      ...(searchedModules.has("gebiz")
        ? [toFreshness("GeBIZ", observedAt, getFirstTimestamp(tenders as readonly Readonly<Record<string, unknown>>[], ["awardDate"]))]
        : []),
      ...(searchedModules.has("boa")
        ? [
            toFreshness("BOA architects", observedAt, null),
            toFreshness("BOA architecture firms", observedAt, null),
          ]
        : []),
      ...(searchedModules.has("hsa")
        ? [
            toFreshness("HSA licensed pharmacies", observedAt, null),
            toFreshness("HSA health product licensees", observedAt, getFirstTimestamp(licensees as readonly Readonly<Record<string, unknown>>[], ["expiryDate"])),
          ]
        : []),
      ...(searchedModules.has("hlb")
        ? [toFreshness("HLB hotels", observedAt, getFirstTimestamp(hotels as readonly Readonly<Record<string, unknown>>[], ["lastUpdatedAt"]))]
        : []),
      ...externalArtifacts.flatMap((artifact) => artifact.freshness),
    ],
    limits: finalLimits,
    sourceCoverage,
    riskFlags: finalRiskFlags,
    matchConfidence,
    analystFollowUps,
    nextChecks,
  };
  return withDossierAnalystFollowUps(artifact);
};
