import type {
  BcaLicensedBuilderRecord,
  BcaNormalizedLicensedBuilderRecord,
  BcaNormalizedRegisteredContractorRecord,
  BcaRegisteredContractorRecord,
} from "@dude/shared";
import { queryDatastoreExactMatches } from "../datagov/client.js";
import { scoreBusinessNameMatch } from "../../diligence/name-matching.js";

const LICENSED_BUILDERS_RESOURCE_ID = "d_19573c579879be15623f2e1e3854926d";
const REGISTERED_CONTRACTORS_RESOURCE_ID = "d_dcda79be4aded5f9e769b8e23ff69b47";

type BcaLicensedBuilderFilterParams = {
  readonly companyName?: string | undefined;
  readonly uenNo?: string | undefined;
  readonly className?: string | undefined;
  readonly classCode?: string | undefined;
  readonly limit?: number | undefined;
};

type BcaRegisteredContractorFilterParams = {
  readonly companyName?: string | undefined;
  readonly uenNo?: string | undefined;
  readonly workhead?: string | undefined;
  readonly grade?: string | undefined;
  readonly limit?: number | undefined;
};

const normalizeFilter = (value: string | undefined): string | undefined => {
  const normalized = value?.trim();
  return normalized === "" ? undefined : normalized;
};

const normalizeCompare = (value: string): string =>
  value
    .trim()
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const exactMatches = (actual: string, expected: string | undefined): boolean => {
  return expected === undefined || normalizeCompare(actual) === normalizeCompare(expected);
};

const nameMatches = (actual: string, expected: string | undefined): boolean =>
  expected === undefined || scoreBusinessNameMatch(expected, actual).matches;

const nullableString = (value: string): string | null => {
  const normalized = value.trim();
  return normalized === "" ? null : normalized;
};

const getQueryLimit = (limit?: number): number => Math.min(Math.max(limit ?? 25, 1), 100);

const buildLicensedBuilderFilters = (
  params: BcaLicensedBuilderFilterParams,
): Readonly<Record<string, unknown>> => {
  const uenNo = normalizeFilter(params.uenNo);
  return {
    ...(params.companyName === undefined || uenNo !== undefined
      ? {}
      : { company_name: { ilike: normalizeFilter(params.companyName)! } }),
    ...(uenNo === undefined ? {} : { uen_no: uenNo.toUpperCase() }),
    ...(params.className === undefined ? {} : { class: { ilike: normalizeFilter(params.className)! } }),
    ...(params.classCode === undefined ? {} : { class_code: { ilike: normalizeFilter(params.classCode)! } }),
  };
};

const buildRegisteredContractorFilters = (
  params: BcaRegisteredContractorFilterParams,
): Readonly<Record<string, unknown>> => {
  const uenNo = normalizeFilter(params.uenNo);
  return {
    ...(params.companyName === undefined || uenNo !== undefined
      ? {}
      : { company_name: { ilike: normalizeFilter(params.companyName)! } }),
    ...(uenNo === undefined ? {} : { uen_no: uenNo.toUpperCase() }),
    ...(params.workhead === undefined ? {} : { workhead: { ilike: normalizeFilter(params.workhead)! } }),
    ...(params.grade === undefined ? {} : { grade: { ilike: normalizeFilter(params.grade)! } }),
  };
};

export const getBcaLicensedBuilders = async (
  params: BcaLicensedBuilderFilterParams,
): Promise<readonly BcaNormalizedLicensedBuilderRecord[]> => {
  const rows = await queryDatastoreExactMatches<BcaLicensedBuilderRecord>(LICENSED_BUILDERS_RESOURCE_ID, {
    matchLimit: getQueryLimit(params.limit),
    filters: buildLicensedBuilderFilters(params),
    sort: "company_name asc",
    exactMatch: (row) =>
      nameMatches(row.company_name, params.companyName)
      && exactMatches(row.uen_no, params.uenNo)
      && exactMatches(row.class, params.className)
      && exactMatches(row.class_code, params.classCode),
  });

  return rows
    .map((row) => ({
      companyName: row.company_name,
      uenNo: row.uen_no,
      className: row.class,
      classCode: row.class_code,
      additionalInfo: nullableString(row.additional_info),
      expiryDate: row.expiry_date,
      buildingNo: row.building_no,
      streetName: row.street_name,
      unitNo: nullableString(row.unit_no),
      buildingName: nullableString(row.building_name),
      postalCode: row.postal_code,
      telNo: row.tel_no,
    }))
    .slice(0, params.limit ?? 25);
};

export const getBcaRegisteredContractors = async (
  params: BcaRegisteredContractorFilterParams,
): Promise<readonly BcaNormalizedRegisteredContractorRecord[]> => {
  const rows = await queryDatastoreExactMatches<BcaRegisteredContractorRecord>(REGISTERED_CONTRACTORS_RESOURCE_ID, {
    matchLimit: getQueryLimit(params.limit),
    filters: buildRegisteredContractorFilters(params),
    sort: "company_name asc",
    exactMatch: (row) =>
      nameMatches(row.company_name, params.companyName)
      && exactMatches(row.uen_no, params.uenNo)
      && exactMatches(row.workhead, params.workhead)
      && exactMatches(row.grade, params.grade),
  });

  return rows
    .map((row) => ({
      companyName: row.company_name,
      uenNo: row.uen_no,
      workhead: row.workhead,
      grade: row.grade,
      additionalInfo: nullableString(row.additional_info),
      expiryDate: row.expiry_date,
      buildingNo: nullableString(row.building_no),
      streetName: row.street_name,
      unitNo: nullableString(row.unit_no),
      buildingName: nullableString(row.building_name),
      postalCode: row.postal_code,
      telNo: row.tel_no,
    }))
    .slice(0, params.limit ?? 25);
};
