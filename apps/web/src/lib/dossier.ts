import type {
  BriefFreshnessItem,
  BriefSummaryItem,
  BusinessDossier,
  BusinessDossierModule,
  MatchConfidence,
  RiskFlag,
  SourceCoverageItem,
} from "@/types/dossier";

export type DossierRecordGroup = {
  module: BusinessDossierModule;
  label: string;
  tables: {
    label: string;
    records: Record<string, unknown>[];
  }[];
};

export const BUSINESS_MODULE_LABELS: Record<BusinessDossierModule, string> = {
  acra: "ACRA",
  bca: "BCA",
  boa: "BOA",
  cea: "CEA",
  gebiz: "GeBIZ",
  hlb: "HLB",
  hsa: "HSA",
};

export const UEN_PATTERN = /^(?:\d{8,9}[a-z]|[a-z]\d{2}[a-z]{2}\d{4}[a-z])$/i;
export type FollowUpBusinessModule = Exclude<BusinessDossierModule, "acra">;
export const ALL_FOLLOW_UP_BUSINESS_MODULES: readonly FollowUpBusinessModule[] = [
  "bca",
  "cea",
  "gebiz",
  "boa",
  "hsa",
  "hlb",
] as const;

export const BUSINESS_MODULE_FOLLOW_UPS: Record<FollowUpBusinessModule, {
  helperText: string;
  inputLabel: string;
  placeholder: string;
  sectorHint: string;
}> = {
  bca: {
    helperText: "Needs construction context plus a company name, UEN, class code, workhead, or grade.",
    inputLabel: "Construction company name or UEN",
    placeholder: "Example Builders Pte Ltd",
    sectorHint: "construction",
  },
  boa: {
    helperText: "Needs architecture context plus a firm, architect name, or registration number.",
    inputLabel: "Architecture firm, architect, or registration no.",
    placeholder: "Example Architects LLP",
    sectorHint: "architecture",
  },
  cea: {
    helperText: "Needs real-estate context plus a salesperson registration number, agent licence, or estate-agent name.",
    inputLabel: "CEA registration, licence, or estate-agent name",
    placeholder: "R123456A or Example Realty Pte Ltd",
    sectorHint: "real_estate",
  },
  gebiz: {
    helperText: "Needs procurement context plus the supplier or entity name used in GeBIZ awards.",
    inputLabel: "GeBIZ supplier name",
    placeholder: "Example Supplier Pte Ltd",
    sectorHint: "procurement",
  },
  hlb: {
    helperText: "Needs hospitality context plus a hotel, keeper, or entity name.",
    inputLabel: "Hotel or keeper name",
    placeholder: "Example Hotel Pte Ltd",
    sectorHint: "hospitality",
  },
  hsa: {
    helperText: "Needs healthcare context plus a company or pharmacy name.",
    inputLabel: "Healthcare company or pharmacy name",
    placeholder: "Example Health Pte Ltd",
    sectorHint: "healthcare",
  },
};

export function buildBusinessDossierInput(identifier: string): { uen: string } | { entityName: string } {
  const trimmed = identifier.trim();
  return UEN_PATTERN.test(trimmed) ? { uen: trimmed.toUpperCase() } : { entityName: trimmed };
}

export function buildBusinessDossierFollowUpInput(params: {
  dossier: BusinessDossier;
  identifier: string;
  module: FollowUpBusinessModule;
  value: string;
}): Record<string, unknown> {
  const value = params.value.trim();
  if (value === "") {
    throw new Error("Follow-up input is required.");
  }

  const base = buildBusinessDossierInput(params.identifier);
  const summaryUen = getSummaryString(params.dossier, "UEN");
  const summaryEntity = getSummaryString(params.dossier, "Entity");
  const input: Record<string, unknown> = {
    ...base,
    modules: Array.from(new Set<BusinessDossierModule>(["acra", params.module])),
    sectorHints: [BUSINESS_MODULE_FOLLOW_UPS[params.module].sectorHint],
  };

  if (summaryUen !== null && UEN_PATTERN.test(summaryUen)) {
    input.uen = summaryUen.toUpperCase();
  }
  if (summaryEntity !== null) {
    input.entityName = summaryEntity;
  }

  if (params.module === "cea") {
    if (/^r\d+/i.test(value)) {
      input.registrationNo = value.toUpperCase();
    } else if (/^l\d+/i.test(value)) {
      input.estateAgentLicenseNo = value.toUpperCase();
    } else {
      input.estateAgentName = value;
    }
    return input;
  }

  if (params.module === "boa") {
    if (/^[a-z]?\d{2,}[a-z]?$/i.test(value)) {
      input.registrationNo = value.toUpperCase();
    } else {
      input.entityName = value;
    }
    return input;
  }

  if (params.module === "bca" && UEN_PATTERN.test(value)) {
    input.uen = value.toUpperCase();
    return input;
  }

  input.entityName = value;
  return input;
}

export function buildBusinessDossierExpandedInput(params: {
  dossier: BusinessDossier;
  identifier: string;
  modules?: readonly FollowUpBusinessModule[];
  value: string;
}): Record<string, unknown> {
  const value = params.value.trim();
  const modules = params.modules === undefined || params.modules.length === 0
    ? ALL_FOLLOW_UP_BUSINESS_MODULES
    : params.modules;
  const base = buildBusinessDossierInput(params.identifier);
  const summaryUen = getSummaryString(params.dossier, "UEN");
  const summaryEntity = getSummaryString(params.dossier, "Entity");
  const entityName = summaryEntity ?? (value !== "" && !UEN_PATTERN.test(value) ? value : null);
  const input: Record<string, unknown> = {
    ...base,
    modules: Array.from(new Set<BusinessDossierModule>(["acra", ...modules])),
    sectorHints: Array.from(new Set(modules.map((module) => BUSINESS_MODULE_FOLLOW_UPS[module].sectorHint))),
  };

  if (summaryUen !== null && UEN_PATTERN.test(summaryUen)) {
    input.uen = summaryUen.toUpperCase();
  }
  if (entityName !== null) {
    input.entityName = entityName;
  }
  if (modules.includes("cea") && entityName !== null) {
    input.estateAgentName = entityName;
  }

  return input;
}

export function sanitizeFilenamePart(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "counterparty";
}

export function formatLabel(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isDateLikeKey(key: string): boolean {
  return /date|timestamp|observed|updated|verified|expiry|start|end|incorporation|registration/i.test(key);
}

export function formatTimestamp(value: unknown): string | null {
  if (typeof value !== "string" || value.trim() === "") {
    return null;
  }
  const trimmed = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}/.test(trimmed)) {
    return null;
  }
  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const hasTime = /t|\d{2}:\d{2}/i.test(trimmed);
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    ...(hasTime ? { timeStyle: "short" } : {}),
  }).format(date);
}

export function formatRecordValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "string" && isDateLikeKey(key)) {
    return formatTimestamp(value) ?? value;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? "-" : value.map((item) => formatRecordValue(key, item)).join(", ");
  }
  return JSON.stringify(value);
}

export function getSummaryValue(summary: BriefSummaryItem[], label: string): unknown {
  return summary.find((item) => item.label.toLowerCase() === label.toLowerCase())?.value;
}

export function getSummaryString(dossier: BusinessDossier, label: string): string | null {
  const value = getSummaryValue(dossier.summary, label);
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

export function buildSummaryLine(dossier: BusinessDossier): string {
  const entity = getSummaryValue(dossier.summary, "Entity");
  const uen = getSummaryValue(dossier.summary, "UEN");
  const status = getSummaryValue(dossier.summary, "Entity status");
  const parts = [
    typeof entity === "string" && entity.trim() !== "" ? entity : null,
    typeof uen === "string" && uen.trim() !== "" ? `UEN ${uen}` : null,
    typeof status === "string" && status.trim() !== "" ? status : null,
  ].filter(Boolean);

  return parts.length > 0
    ? parts.join(" - ")
    : "Registry evidence returned for the requested counterparty.";
}

export function isNotFoundDossier(dossier: BusinessDossier): boolean {
  const matchedModules = dossier.records.resolution?.matchedModules;
  if (Array.isArray(matchedModules)) {
    return matchedModules.length === 0;
  }

  return getDossierRecordGroups(dossier).every((group) =>
    group.tables.every((table) => table.records.length === 0),
  );
}

const asRecords = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
        item !== null && typeof item === "object" && !Array.isArray(item),
      )
    : [];

export function getDossierRecordGroups(dossier: BusinessDossier): DossierRecordGroup[] {
  const records = dossier.records;
  const groups: DossierRecordGroup[] = [
    {
      module: "acra",
      label: BUSINESS_MODULE_LABELS.acra,
      tables: [{ label: "Entity records", records: asRecords(records.acra) }],
    },
    {
      module: "bca",
      label: BUSINESS_MODULE_LABELS.bca,
      tables: [
        { label: "Licensed builders", records: asRecords(records.bcaLicensedBuilders) },
        { label: "Registered contractors", records: asRecords(records.bcaRegisteredContractors) },
      ],
    },
    {
      module: "cea",
      label: BUSINESS_MODULE_LABELS.cea,
      tables: [{ label: "Salespersons and estate agents", records: asRecords(records.ceaSalespersons) }],
    },
    {
      module: "gebiz",
      label: BUSINESS_MODULE_LABELS.gebiz,
      tables: [{ label: "Tender awards", records: asRecords(records.gebizTenders) }],
    },
    {
      module: "boa",
      label: BUSINESS_MODULE_LABELS.boa,
      tables: [
        { label: "Architects", records: asRecords(records.boaArchitects) },
        { label: "Architecture firms", records: asRecords(records.boaArchitectureFirms) },
      ],
    },
    {
      module: "hsa",
      label: BUSINESS_MODULE_LABELS.hsa,
      tables: [
        { label: "Licensed pharmacies", records: asRecords(records.hsaLicensedPharmacies) },
        { label: "Health-product licensees", records: asRecords(records.hsaHealthProductLicensees) },
      ],
    },
    {
      module: "hlb",
      label: BUSINESS_MODULE_LABELS.hlb,
      tables: [{ label: "Hotels", records: asRecords(records.hlbHotels) }],
    },
  ];

  return groups.filter((group) => {
    const visibleModules = dossier.records.resolution?.searchedModules
      ?? dossier.records.resolution?.selectedModules;
    return visibleModules === undefined || visibleModules.includes(group.module);
  });
}

export function getSourceCoverage(dossier: BusinessDossier): SourceCoverageItem[] {
  return dossier.sourceCoverage ?? [];
}

export function sourceCoverageStatusLabel(status: SourceCoverageItem["status"]): string {
  if (status === "credential_blocked") return "Credential blocked";
  if (status === "not_applicable") return "Not applicable";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function sourceCoverageLevelLabel(level: SourceCoverageItem["coverageLevel"]): string {
  return level.charAt(0).toUpperCase() + level.slice(1);
}

export function getFreshnessForSource(
  freshness: BriefFreshnessItem[],
  source: string,
): BriefFreshnessItem | undefined {
  const normalizedSource = source.toLowerCase();
  return freshness.find((item) => item.source.toLowerCase().includes(normalizedSource));
}

export type DiligenceSnapshot = {
  entityName: string | null;
  uen: string | null;
  status: string | null;
  entityType: string | null;
  age: string | null;
  address: string | null;
  primarySsic: string | null;
  matchedModules: string;
  confidence: string | null;
};

export type DossierConfidence = {
  level: string;
  score?: number;
  rationale?: string;
  identity?: {
    level?: string;
    score?: number;
    primarySource?: string | null;
    matchedOn?: string | null;
    rationale?: string;
  };
  coverage?: {
    selectedModules?: string[];
    searchedModules?: string[];
    matchedModules?: string[];
    unmatchedModules?: string[];
    unsearchedModules?: string[];
    score?: number;
    rationale?: string;
  };
};

const firstRecord = (value: unknown): Record<string, unknown> | null =>
  Array.isArray(value) && value[0] !== null && typeof value[0] === "object" && !Array.isArray(value[0])
    ? value[0] as Record<string, unknown>
    : null;

export function getPrimaryAcraRecord(dossier: BusinessDossier): Record<string, unknown> | null {
  return firstRecord(dossier.records.acra);
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

function asStringArray(value: unknown): string[] | undefined {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : undefined;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function getEntityAge(registrationDate: string | null): string | null {
  if (registrationDate === null) {
    return null;
  }
  const date = new Date(registrationDate);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const years = Math.max(0, new Date().getFullYear() - date.getFullYear());
  return years === 1 ? "1 year" : `${years} years`;
}

function getAddress(record: Record<string, unknown> | null): string | null {
  if (record === null) {
    return null;
  }
  const parts = [
    asString(record["block"]),
    asString(record["streetName"]),
    asString(record["buildingName"]),
    asString(record["postalCode"]) === null ? null : `Singapore ${asString(record["postalCode"])}`,
  ].filter(Boolean);
  return parts.length === 0 ? null : parts.join(", ");
}

export function getDossierConfidence(dossier: BusinessDossier): DossierConfidence | null {
  const value = dossier.records.quality?.["dossierConfidence"];
  const record = asRecord(value);
  if (record === null) {
    return null;
  }
  const level = asString(record["level"]);
  if (level === null) {
    return null;
  }
  const score = typeof record["score"] === "number" ? record["score"] : undefined;
  const rationale = asString(record["rationale"]) ?? undefined;
  const identity = asRecord(record["identity"]);
  const coverage = asRecord(record["coverage"]);
  return {
    level,
    ...(score === undefined ? {} : { score }),
    ...(rationale === undefined ? {} : { rationale }),
    ...(identity === null
      ? {}
      : {
          identity: {
            level: asString(identity["level"]) ?? undefined,
            score: typeof identity["score"] === "number" ? identity["score"] : undefined,
            primarySource: asString(identity["primarySource"]),
            matchedOn: asString(identity["matchedOn"]),
            rationale: asString(identity["rationale"]) ?? undefined,
          },
        }),
    ...(coverage === null
      ? {}
      : {
          coverage: {
            selectedModules: asStringArray(coverage["selectedModules"]),
            searchedModules: asStringArray(coverage["searchedModules"]),
            matchedModules: asStringArray(coverage["matchedModules"]),
            unmatchedModules: asStringArray(coverage["unmatchedModules"]),
            unsearchedModules: asStringArray(coverage["unsearchedModules"]),
            score: typeof coverage["score"] === "number" ? coverage["score"] : undefined,
            rationale: asString(coverage["rationale"]) ?? undefined,
          },
        }),
  };
}

export function buildDiligenceSnapshot(dossier: BusinessDossier): DiligenceSnapshot {
  const acra = getPrimaryAcraRecord(dossier);
  const confidence = getDossierConfidence(dossier);
  const primarySsicCode = asString(acra?.["primarySsicCode"]);
  const primarySsicDescription = asString(acra?.["primarySsicDescription"]);
  return {
    entityName: asString(acra?.["entityName"]) ?? getSummaryString(dossier, "Entity"),
    uen: asString(acra?.["uen"]) ?? getSummaryString(dossier, "UEN"),
    status: asString(acra?.["entityStatusDescription"]) ?? getSummaryString(dossier, "Entity status"),
    entityType: asString(acra?.["entityTypeDescription"]),
    age: getEntityAge(asString(acra?.["registrationIncorporationDate"])),
    address: getAddress(acra),
    primarySsic: primarySsicCode === null
      ? null
      : `${primarySsicCode}${primarySsicDescription === null ? "" : ` - ${primarySsicDescription}`}`,
    matchedModules: dossier.records.resolution?.matchedModules?.join(", ") || "none",
    confidence: confidence === null
      ? null
      : `${confidence.level}${confidence.score === undefined ? "" : ` (${Math.round(confidence.score * 100)}%)`}`,
  };
}

export function getSectorBadges(dossier: BusinessDossier): string[] {
  const acra = getPrimaryAcraRecord(dossier);
  const ssic = asString(acra?.["primarySsicCode"]);
  const modules = dossier.records.resolution?.selectedModules ?? [];
  const badges = new Set<string>();

  if (ssic?.startsWith("41") || ssic?.startsWith("42") || ssic?.startsWith("43")) badges.add("construction");
  if (ssic?.startsWith("46")) badges.add("wholesale");
  if (ssic?.startsWith("47")) badges.add("retail");
  if (ssic?.startsWith("55")) badges.add("hospitality");
  if (ssic?.startsWith("64")) badges.add("finance");
  if (ssic?.startsWith("68")) badges.add("real estate");
  if (ssic?.startsWith("71")) badges.add("architecture / engineering");
  if (ssic?.startsWith("86")) badges.add("healthcare");
  if (modules.includes("gebiz")) badges.add("procurement");
  if (modules.includes("hsa")) badges.add("healthcare");
  if (modules.includes("hlb")) badges.add("hospitality");
  if (modules.includes("boa")) badges.add("architecture");

  return Array.from(badges);
}

export function riskSeverityLabel(flag: RiskFlag): string {
  if (flag.severity === "high") return "High";
  if (flag.severity === "medium") return "Medium";
  return "Low";
}

const RISK_CODE_ACRONYMS = new Set([
  "acra",
  "api",
  "bca",
  "boa",
  "cpf",
  "hdb",
  "hlb",
  "hsa",
  "http",
  "lta",
  "mas",
  "mom",
  "nea",
  "uen",
  "ura",
]);

export function riskCodeLabel(code: string): string {
  const words = code.split(/[_\s-]+/).filter((word) => word.length > 0);
  if (words.length === 0) {
    return "Risk signal";
  }

  return words
    .map((word, index) => {
      const lower = word.toLowerCase();
      if (RISK_CODE_ACRONYMS.has(lower)) {
        return lower.toUpperCase();
      }
      return index === 0 ? `${lower.charAt(0).toUpperCase()}${lower.slice(1)}` : lower;
    })
    .join(" ");
}

export function confidenceLabel(confidence: MatchConfidence["confidence"]): string {
  if (confidence === "name-exact") return "Name exact";
  if (confidence === "name-fuzzy") return "Name fuzzy";
  if (confidence === "no-match") return "No match";
  return "Exact";
}
