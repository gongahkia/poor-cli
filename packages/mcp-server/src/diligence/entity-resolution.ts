import type { MatchConfidence } from "@sg-apis/shared";

export type BusinessDossierModule = "acra" | "bca" | "cea" | "gebiz" | "boa" | "hsa" | "hlb";
export type BusinessSectorHint =
  | "construction"
  | "real_estate"
  | "architecture"
  | "healthcare"
  | "hospitality"
  | "procurement";

export const DEFAULT_BUSINESS_DOSSIER_MODULES: readonly BusinessDossierModule[] = [
  "acra",
  "bca",
  "cea",
] as const;

const MODULES_BY_SECTOR: Readonly<Record<BusinessSectorHint, readonly BusinessDossierModule[]>> = {
  construction: ["bca"],
  real_estate: ["cea"],
  architecture: ["boa"],
  healthcare: ["hsa"],
  hospitality: ["hlb"],
  procurement: ["gebiz"],
};

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

export const normalizeBusinessName = (value: string | undefined): string => {
  return (value ?? "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
};

const tokenizeBusinessName = (value: string): readonly string[] => {
  return normalizeBusinessName(value)
    .split(" ")
    .filter((token) => token.length >= 2);
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
        if (candidate !== null && isBoundedFuzzyBusinessNameMatch(nameInput.value, candidate)) {
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
