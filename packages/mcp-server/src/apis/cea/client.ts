import type {
  CeaNormalizedSalespersonRecord,
  CeaSalespersonRecord,
} from "@sg-apis/shared";
import { queryDatastoreExactMatches } from "../datagov/client.js";

const SALESPEOPLE_RESOURCE_ID = "d_07c63be0f37e6e59c07a4ddc2fd87fcb";

type CeaFilterParams = {
  readonly salespersonName?: string | undefined;
  readonly registrationNo?: string | undefined;
  readonly estateAgentName?: string | undefined;
  readonly estateAgentLicenseNo?: string | undefined;
  readonly limit?: number | undefined;
};

const normalizeFilter = (value: string | undefined): string | undefined => {
  const normalized = value?.trim();
  return normalized === "" ? undefined : normalized;
};

const normalizeCompare = (value: string): string => value.trim().toLowerCase();

const exactMatches = (actual: string, expected: string | undefined): boolean => {
  return expected === undefined || normalizeCompare(actual) === normalizeCompare(expected);
};

const buildDatastoreFilters = (params: CeaFilterParams): Readonly<Record<string, unknown>> => ({
  ...(params.salespersonName === undefined
    ? {}
    : { salesperson_name: { ilike: normalizeFilter(params.salespersonName)! } }),
  ...(params.registrationNo === undefined
    ? {}
    : { registration_no: { ilike: normalizeFilter(params.registrationNo)! } }),
  ...(params.estateAgentName === undefined
    ? {}
    : { estate_agent_name: { ilike: normalizeFilter(params.estateAgentName)! } }),
  ...(params.estateAgentLicenseNo === undefined
    ? {}
    : { estate_agent_license_no: { ilike: normalizeFilter(params.estateAgentLicenseNo)! } }),
});

const getQueryLimit = (limit?: number): number => Math.min(Math.max(limit ?? 25, 1), 100);

export const getCeaSalespersons = async (
  params: CeaFilterParams,
): Promise<readonly CeaNormalizedSalespersonRecord[]> => {
  const rows = await queryDatastoreExactMatches<CeaSalespersonRecord>(SALESPEOPLE_RESOURCE_ID, {
    matchLimit: getQueryLimit(params.limit),
    filters: buildDatastoreFilters(params),
    sort: "salesperson_name asc",
    exactMatch: (row) =>
      exactMatches(row.salesperson_name, params.salespersonName)
      && exactMatches(row.registration_no, params.registrationNo)
      && exactMatches(row.estate_agent_name, params.estateAgentName)
      && exactMatches(row.estate_agent_license_no, params.estateAgentLicenseNo),
  });

  return rows
    .map((row) => ({
      salespersonName: row.salesperson_name,
      registrationNo: row.registration_no,
      registrationStartDate: row.registration_start_date,
      registrationEndDate: row.registration_end_date,
      estateAgentName: row.estate_agent_name,
      estateAgentLicenseNo: row.estate_agent_license_no,
    }))
    .slice(0, params.limit ?? 25);
};
