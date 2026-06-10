import type {
  BoaArchitectRecord,
  BoaArchitectureFirmRecord,
  BoaNormalizedArchitectRecord,
  BoaNormalizedArchitectureFirmRecord,
} from "@swee-sg/shared";
import { downloadDatasetCsvRows } from "../datagov/client.js";
import { toNullableString } from "../civic/utils.js";
import { scoreBusinessNameMatch } from "../../diligence/name-matching.js";

const BOA_ARCHITECTS_DATASET_ID = "d_d77de0f78ca589a5c61da7a60fdee6ba";
const BOA_ARCHITECTURE_FIRMS_DATASET_ID = "d_d5c0a4ffd076a3e40d772275619bbb66";

const normalizeString = (value: unknown): string => {
  return typeof value === "string" ? value.trim() : "";
};

const normalizeCompare = (value: unknown): string => {
  return normalizeString(value)
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
};

const exactMatches = (actual: unknown, expected: string | undefined): boolean => {
  return expected === undefined || normalizeCompare(actual) === normalizeCompare(expected);
};

const nameMatches = (actual: unknown, expected: string | undefined): boolean =>
  expected === undefined || scoreBusinessNameMatch(expected, normalizeString(actual)).matches;

const getLimit = (value: number | undefined): number => Math.min(Math.max(value ?? 50, 1), 100);

const field = (row: Readonly<Record<string, unknown>>, keys: readonly string[]): unknown => {
  let firstDefined: unknown;
  for (const key of keys) {
    const value = row[key];
    if (value === undefined) {
      continue;
    }
    firstDefined ??= value;
    if (typeof value === "string" && value.trim() !== "") {
      return value;
    }
  }
  return firstDefined;
};

const requiredString = (value: unknown): string | null => {
  const normalized = normalizeString(value);
  return normalized === "" ? null : normalized;
};

const normalizeArchitect = (row: BoaArchitectRecord): BoaNormalizedArchitectRecord | null => {
  const fields = row as Readonly<Record<string, unknown>>;
  const architectName = requiredString(field(fields, ["me", "name"]));
  const registrationNo = requiredString(field(fields, ["reg_no"]));
  if (architectName === null || registrationNo === null) {
    return null;
  }

  return {
    architectName,
    registrationNo,
    firmName: toNullableString(field(fields, ["firm_me", "firm_name"])),
    firmAddress: toNullableString(field(fields, ["firm_address"])),
    firmPhone: toNullableString(field(fields, ["firm_phone"])),
  };
};

const normalizeArchitectureFirm = (row: BoaArchitectureFirmRecord): BoaNormalizedArchitectureFirmRecord | null => {
  const fields = row as Readonly<Record<string, unknown>>;
  const firmName = requiredString(field(fields, ["firm_me", "firm_name"]));
  if (firmName === null) {
    return null;
  }

  return {
    firmName,
    firmAddress: toNullableString(field(fields, ["firm_address"])),
    firmPhone: toNullableString(field(fields, ["firm_phone"])),
    firmFax: toNullableString(field(fields, ["firm_fax"])),
    firmEmail: toNullableString(field(fields, ["firm_email"])),
  };
};

export const getBoaArchitects = async (
  params: Readonly<{
    name?: string | undefined;
    registrationNo?: string | undefined;
    firmName?: string | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly BoaNormalizedArchitectRecord[]> => {
  const rows = await downloadDatasetCsvRows<BoaArchitectRecord>(BOA_ARCHITECTS_DATASET_ID, "DAILY");
  return rows
    .map(normalizeArchitect)
    .filter((row): row is BoaNormalizedArchitectRecord => row !== null)
    .filter((row) =>
      nameMatches(row.architectName, params.name)
      && exactMatches(row.registrationNo, params.registrationNo)
      && nameMatches(row.firmName, params.firmName),
    )
    .sort((left, right) => left.architectName.localeCompare(right.architectName))
    .slice(0, getLimit(params.limit));
};

export const getBoaArchitectureFirms = async (
  params: Readonly<{
    firmName?: string | undefined;
    email?: string | undefined;
    phone?: string | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly BoaNormalizedArchitectureFirmRecord[]> => {
  const rows = await downloadDatasetCsvRows<BoaArchitectureFirmRecord>(BOA_ARCHITECTURE_FIRMS_DATASET_ID, "DAILY");
  return rows
    .map(normalizeArchitectureFirm)
    .filter((row): row is BoaNormalizedArchitectureFirmRecord => row !== null)
    .filter((row) =>
      nameMatches(row.firmName, params.firmName)
      && exactMatches(row.firmEmail, params.email)
      && exactMatches(row.firmPhone, params.phone),
    )
    .sort((left, right) => left.firmName.localeCompare(right.firmName))
    .slice(0, getLimit(params.limit));
};
