import type {
  BoaArchitectRecord,
  BoaArchitectureFirmRecord,
  BoaNormalizedArchitectRecord,
  BoaNormalizedArchitectureFirmRecord,
} from "@dude/shared";
import { downloadDatasetCsvRows } from "../datagov/client.js";
import { toNullableString } from "../civic/utils.js";

const BOA_ARCHITECTS_DATASET_ID = "d_d77de0f78ca589a5c61da7a60fdee6ba";
const BOA_ARCHITECTURE_FIRMS_DATASET_ID = "d_d5c0a4ffd076a3e40d772275619bbb66";

const normalizeCompare = (value: string | undefined): string => {
  return (value ?? "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
};

const exactMatches = (actual: string, expected: string | undefined): boolean => {
  return expected === undefined || normalizeCompare(actual) === normalizeCompare(expected);
};

const getLimit = (value: number | undefined): number => Math.min(Math.max(value ?? 50, 1), 100);

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
    .filter((row) =>
      exactMatches(row.me, params.name)
      && exactMatches(row.reg_no, params.registrationNo)
      && exactMatches(row.firm_me, params.firmName),
    )
    .map((row) => ({
      architectName: row.me.trim(),
      registrationNo: row.reg_no.trim(),
      firmName: toNullableString(row.firm_me),
      firmAddress: toNullableString(row.firm_address),
      firmPhone: toNullableString(row.firm_phone),
    }))
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
    .filter((row) =>
      exactMatches(row.firm_me, params.firmName)
      && exactMatches(row.firm_email, params.email)
      && exactMatches(row.firm_phone, params.phone),
    )
    .map((row) => ({
      firmName: row.firm_me.trim(),
      firmAddress: toNullableString(row.firm_address),
      firmPhone: toNullableString(row.firm_phone),
      firmFax: toNullableString(row.firm_fax),
      firmEmail: toNullableString(row.firm_email),
    }))
    .sort((left, right) => left.firmName.localeCompare(right.firmName))
    .slice(0, getLimit(params.limit));
};
