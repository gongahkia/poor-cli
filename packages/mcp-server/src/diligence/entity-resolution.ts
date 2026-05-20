import type { MatchConfidence } from "@dude/shared";
import {
  isBusinessNameMatch,
  normalizeBusinessNameForSearch,
  tokenizeBusinessName as tokenizeMatchedBusinessName,
} from "./name-matching.js";

export type BusinessDossierModule = "acra" | "bca" | "cea" | "gebiz" | "boa" | "hsa" | "hlb";
export type BusinessSectorHint =
  | "construction"
  | "real_estate"
  | "architecture"
  | "healthcare"
  | "hospitality"
  | "procurement";

export type InferredBusinessSector = Readonly<{
  sector: BusinessSectorHint;
  source: "ACRA";
  evidence: string;
  modules: readonly BusinessDossierModule[];
}>;

export const ALL_BUSINESS_DOSSIER_MODULES: readonly BusinessDossierModule[] = [
  "acra",
  "bca",
  "cea",
  "gebiz",
  "boa",
  "hsa",
  "hlb",
] as const;

export const DEFAULT_BUSINESS_DOSSIER_MODULES: readonly BusinessDossierModule[] = [
  "acra",
] as const;

const MODULES_BY_SECTOR: Readonly<Record<BusinessSectorHint, readonly BusinessDossierModule[]>> = {
  construction: ["bca"],
  real_estate: ["cea"],
  architecture: ["boa"],
  healthcare: ["hsa"],
  hospitality: ["hlb"],
  procurement: ["gebiz"],
};

export const getBusinessModulesForSector = (
  sectorHint: BusinessSectorHint,
): readonly BusinessDossierModule[] => MODULES_BY_SECTOR[sectorHint];

export const selectBusinessDossierModules = (
  modules: readonly BusinessDossierModule[] | undefined,
  sectorHints: readonly BusinessSectorHint[] | undefined,
): readonly BusinessDossierModule[] => {
  const selected = new Set<BusinessDossierModule>(modules ?? DEFAULT_BUSINESS_DOSSIER_MODULES);

  for (const sectorHint of sectorHints ?? []) {
    for (const module of MODULES_BY_SECTOR[sectorHint]) {
      selected.add(module);
    }
  }

  return Array.from(selected);
};

const getRecordString = (
  record: Readonly<Record<string, unknown>>,
  field: string,
): string | null => {
  const value = record[field];
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
};

const inferSectorHintsFromSsic = (
  code: string | null,
  description: string | null,
): readonly BusinessSectorHint[] => {
  const hints = new Set<BusinessSectorHint>();
  const normalizedCode = code ?? "";
  const normalizedDescription = normalizeBusinessName(description ?? "");

  if (/^(41|42|43)/.test(normalizedCode)) hints.add("construction");
  if (/^(711|71)/.test(normalizedCode) || normalizedDescription.includes("architect")) hints.add("architecture");
  if (/^(55)/.test(normalizedCode) || normalizedDescription.includes("hotel")) hints.add("hospitality");
  if (/^(68)/.test(normalizedCode) || normalizedDescription.includes("real estate")) hints.add("real_estate");
  if (
    /^(86|4646|4772)/.test(normalizedCode)
    || normalizedDescription.includes("health")
    || normalizedDescription.includes("medical")
    || normalizedDescription.includes("pharmaceutical")
    || normalizedDescription.includes("pharmacy")
  ) {
    hints.add("healthcare");
  }

  return Array.from(hints);
};

export const inferBusinessSectorsFromAcra = (
  records: readonly Readonly<Record<string, unknown>>[],
): readonly InferredBusinessSector[] => {
  const inferred = new Map<BusinessSectorHint, InferredBusinessSector>();

  for (const record of records) {
    const ssicPairs = [
      {
        code: getRecordString(record, "primarySsicCode"),
        description: getRecordString(record, "primarySsicDescription"),
        label: "primary SSIC",
      },
      {
        code: getRecordString(record, "secondarySsicCode"),
        description: getRecordString(record, "secondarySsicDescription"),
        label: "secondary SSIC",
      },
    ] as const;

    for (const ssic of ssicPairs) {
      for (const sector of inferSectorHintsFromSsic(ssic.code, ssic.description)) {
        if (inferred.has(sector)) continue;
        const evidenceParts = [
          ssic.label,
          ssic.code === null ? null : ssic.code,
          ssic.description === null ? null : ssic.description,
        ].filter(Boolean);
        inferred.set(sector, {
          sector,
          source: "ACRA",
          evidence: evidenceParts.join(": "),
          modules: MODULES_BY_SECTOR[sector],
        });
      }
    }
  }

  return Array.from(inferred.values());
};

export const normalizeBusinessName = (value: string | undefined): string => {
  return normalizeBusinessNameForSearch(value);
};

const tokenizeBusinessName = (value: string): readonly string[] => {
  return tokenizeMatchedBusinessName(value);
};

export const isBoundedFuzzyBusinessNameMatch = (
  expected: string,
  actual: string,
): boolean => {
  const normalizedExpected = normalizeBusinessName(expected);
  const normalizedActual = normalizeBusinessName(actual);

  if (normalizedExpected === "" || normalizedActual === "") {
    return false;
  }

  if (normalizedExpected === normalizedActual) {
    return true;
  }

  if (
    normalizedExpected.length >= 8
    && normalizedActual.length >= 8
    && (normalizedExpected.includes(normalizedActual) || normalizedActual.includes(normalizedExpected))
  ) {
    return true;
  }

  const expectedTokens = tokenizeBusinessName(expected);
  const actualTokens = tokenizeBusinessName(actual);
  if (expectedTokens.length === 0 || actualTokens.length === 0) {
    return false;
  }

  const expectedSet = new Set(expectedTokens);
  const actualSet = new Set(actualTokens);
  let overlap = 0;
  for (const token of expectedSet) {
    if (actualSet.has(token)) {
      overlap += 1;
    }
  }

  const denominator = Math.max(expectedSet.size, actualSet.size);
  return denominator > 0 && overlap / denominator >= 0.75;
};

type ExactInput = {
  readonly value: string;
  readonly fields: readonly string[];
};

type NameInput = {
  readonly value: string;
  readonly fields: readonly string[];
};

export const resolveEntityMatchConfidence = (
  source: string,
  records: readonly Readonly<Record<string, unknown>>[],
  params: Readonly<{
    exactInputs?: readonly ExactInput[];
    nameInputs?: readonly NameInput[];
  }>,
): MatchConfidence => {
  for (const exactInput of params.exactInputs ?? []) {
    for (const record of records) {
      for (const field of exactInput.fields) {
        const candidate = getRecordString(record, field);
        if (candidate !== null && candidate.toUpperCase() === exactInput.value.trim().toUpperCase()) {
          return {
            source,
            confidence: "exact",
            matchedOn: field,
          };
        }
      }
    }
  }

  for (const nameInput of params.nameInputs ?? []) {
    const expected = normalizeBusinessName(nameInput.value);
    for (const record of records) {
      for (const field of nameInput.fields) {
        const candidate = getRecordString(record, field);
        if (candidate !== null && normalizeBusinessName(candidate) === expected) {
          return {
            source,
            confidence: "name-exact",
            matchedOn: field,
          };
        }
      }
    }
  }

  for (const nameInput of params.nameInputs ?? []) {
    for (const record of records) {
      for (const field of nameInput.fields) {
        const candidate = getRecordString(record, field);
        if (candidate !== null && isBusinessNameMatch(nameInput.value, candidate)) {
          return {
            source,
            confidence: "name-fuzzy",
            matchedOn: field,
          };
        }
      }
    }
  }

  return {
    source,
    confidence: "no-match",
    matchedOn: null,
  };
};
