import type {
  BriefFreshnessItem,
  BriefSummaryItem,
  BusinessDossier,
  BusinessDossierModule,
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

export function buildBusinessDossierInput(identifier: string): { uen: string } | { entityName: string } {
  const trimmed = identifier.trim();
  return UEN_PATTERN.test(trimmed) ? { uen: trimmed.toUpperCase() } : { entityName: trimmed };
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
    const selected = dossier.records.resolution?.selectedModules;
    return selected === undefined || selected.includes(group.module);
  });
}

export function getFreshnessForSource(
  freshness: BriefFreshnessItem[],
  source: string,
): BriefFreshnessItem | undefined {
  const normalizedSource = source.toLowerCase();
  return freshness.find((item) => item.source.toLowerCase().includes(normalizedSource));
}
