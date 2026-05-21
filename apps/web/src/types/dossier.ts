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

export type SourceCoverageStatus =
  | "checked"
  | "skipped"
  | "unavailable"
  | "credential_blocked"
  | "not_applicable";

export type SourceCoverageLevel = "full" | "partial" | "none";

export type SourceCoverageItem = {
  family: string;
  label: string;
  tools: string[];
  status: SourceCoverageStatus;
  coverageLevel: SourceCoverageLevel;
  recordCount: number;
  authRequired: boolean;
  reason: string;
  checkedAt?: string | null;
  sourceFreshness?: string | null;
  requiredCredentials?: string[];
  gapCodes?: string[];
  evidenceType?: "official_registry" | "web_discovery" | "operational_metadata";
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
  sourceCoverage?: SourceCoverageItem[];
  riskFlags?: RiskFlag[];
  matchConfidence?: MatchConfidence[];
  analystFollowUps?: AnalystFollowUp[];
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
  status: "matched" | "unmatched" | "needs_identifier" | "unsearched" | "skipped";
  selectedBy: ("default" | "explicit_module" | "sector_hint" | "inferred_sector" | "web_hint" | "analyst_rerun")[];
  searched: boolean;
  matched: boolean;
  reason: string;
  sectorHints?: string[];
  inferredSectors?: string[];
  webSectorHints?: string[];
  requiredIdentifiers?: string[];
  followUpPrompts?: string[];
};

export type InferredBusinessSector = {
  sector: string;
  source: string;
  evidence: string;
  modules: BusinessDossierModule[];
};

export type SectorWorkflowGuideItem = {
  sector: string;
  label: string;
  retainedModules: BusinessDossierModule[];
  retainedTools: string[];
  whyRelevant: string;
  requiredIdentifiers: string[];
  followUpPrompts: string[];
  sourceBoundUse: string;
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

export type AnalystFollowUpPriority = "critical" | "recommended" | "optional";

export type AnalystFollowUpReasonCategory =
  | "identity_confidence"
  | "source_unavailable"
  | "sector_gap"
  | "supplemental_review"
  | "credential_required"
  | "manual_confirmation"
  | "report_quality";

export type AnalystFollowUpEvidenceBasis = {
  kind: "source_gap" | "confidence_blocker" | "skipped_module" | "evidence_limitation";
  ref: string;
  detail: string;
  source?: string | null;
};

export type AnalystFollowUp = {
  id: string;
  priority: AnalystFollowUpPriority;
  category: AnalystFollowUpReasonCategory;
  action: string;
  reason: string;
  whyThisMatters: string;
  evidenceBasis: AnalystFollowUpEvidenceBasis[];
  tool?: string;
  input?: Record<string, unknown>;
};

export type BusinessDossierResolution = {
  requestedEntityName?: string | null;
  requestedUen?: string | null;
  requestedSalespersonName?: string | null;
  requestedRegistrationNo?: string | null;
  selectedModules?: BusinessDossierModule[];
  sectorHints?: string[];
  explicitSectorHints?: string[];
  webSectorHints?: string[];
  analystRerun?: boolean;
  effectiveSectorHints?: string[];
  inferredSectors?: InferredBusinessSector[];
  searchedModules?: BusinessDossierModule[];
  matchedModules?: BusinessDossierModule[];
  unmatchedModules?: BusinessDossierModule[];
  unsearchedModules?: BusinessDossierModule[];
  moduleReasons?: BusinessDossierModuleReason[];
  sectorWorkflowGuide?: SectorWorkflowGuideItem[];
  sectorSelectionContext?: Record<string, unknown>;
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
