export type BriefSummaryItem = {
  label: string;
  value: unknown;
  source?: string | null;
};

export type EvidenceGap = {
  code: string;
  message: string;
};

export type BriefProvenanceItem = {
  source: string;
  tool: string;
  coverage: string;
  authRequired: boolean;
  recordCount: number;
  sourceUrl?: string;
  evidenceType?: "official_registry" | "web_discovery" | "operational_metadata";
};

export type BriefFreshnessItem = {
  source: string;
  observedAt: string;
  upstreamTimestamp?: string | null;
};

export type BriefLimit = {
  code: string;
  message: string;
};

export type BriefArtifact = {
  title: string;
  summary: BriefSummaryItem[];
  evidence: BriefSummaryItem[];
  records: BusinessDossierRecords;
  gaps: EvidenceGap[];
  provenance: BriefProvenanceItem[];
  freshness: BriefFreshnessItem[];
  limits: BriefLimit[];
  riskFlags?: RiskFlag[];
  matchConfidence?: MatchConfidence[];
  nextChecks?: NextCheck[];
};

export type BusinessDossierModule =
  | "acra"
  | "bca"
  | "cea"
  | "gebiz"
  | "boa"
  | "hsa"
  | "hlb";

export type BusinessDossierModuleReason = {
  module: BusinessDossierModule;
  status: "matched" | "unmatched" | "unsearched" | "skipped";
  selectedBy: ("default" | "explicit_module" | "sector_hint" | "inferred_sector")[];
  searched: boolean;
  matched: boolean;
  reason: string;
  sectorHints?: string[];
  inferredSectors?: string[];
};

export type InferredBusinessSector = {
  sector: string;
  source: string;
  evidence: string;
  modules: BusinessDossierModule[];
};

export type RiskFlag = {
  code: string;
  severity: "high" | "medium" | "low";
  message: string;
  source: string;
};

export type MatchConfidence = {
  source: string;
  confidence: "exact" | "name-exact" | "name-fuzzy" | "no-match";
  matchedOn: string | null;
};

export type NextCheck = {
  tool: string;
  reason: string;
  input: Record<string, unknown>;
};

export type BusinessDossierResolution = {
  requestedEntityName?: string | null;
  requestedUen?: string | null;
  requestedSalespersonName?: string | null;
  requestedRegistrationNo?: string | null;
  selectedModules?: BusinessDossierModule[];
  sectorHints?: string[];
  effectiveSectorHints?: string[];
  inferredSectors?: InferredBusinessSector[];
  searchedModules?: BusinessDossierModule[];
  matchedModules?: BusinessDossierModule[];
  unmatchedModules?: BusinessDossierModule[];
  unsearchedModules?: BusinessDossierModule[];
  moduleReasons?: BusinessDossierModuleReason[];
};

export type BusinessDossierRecords = {
  resolution?: BusinessDossierResolution;
  quality?: Record<string, unknown>;
  handoff?: Record<string, unknown>;
  acra?: Record<string, unknown>[];
  bcaLicensedBuilders?: Record<string, unknown>[];
  bcaRegisteredContractors?: Record<string, unknown>[];
  ceaSalespersons?: Record<string, unknown>[];
  gebizTenders?: Record<string, unknown>[];
  boaArchitects?: Record<string, unknown>[];
  boaArchitectureFirms?: Record<string, unknown>[];
  hsaLicensedPharmacies?: Record<string, unknown>[];
  hsaHealthProductLicensees?: Record<string, unknown>[];
  hlbHotels?: Record<string, unknown>[];
  externalDiligence?: Record<string, unknown>[];
};

export type BusinessDossier = BriefArtifact;
