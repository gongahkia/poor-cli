import { queryDatastore, queryDatastoreExactMatches } from "../datagov/client.js";
import { scoreBusinessNameMatch } from "../../diligence/name-matching.js";

const GEBIZ_RESOURCE_ID = "d_c9bea4c28194866ab2e1313e6be430d6";

type GeBIZRawRecord = {
  readonly agency: string;
  readonly tender_no: string;
  readonly tender_description: string;
  readonly award_date: string;
  readonly tender_detail_status: string;
  readonly supplier_name: string;
  readonly awarded_amt: string;
  readonly tender_category: string;
};

export type GeBIZNormalizedRecord = {
  readonly agency: string;
  readonly tenderNo: string;
  readonly description: string;
  readonly awardDate: string;
  readonly status: string;
  readonly supplierName: string;
  readonly awardedAmount: number | null;
  readonly category: string;
};

type GeBIZFilterParams = {
  readonly agency?: string | undefined;
  readonly category?: string | undefined;
  readonly supplierName?: string | undefined;
  readonly limit?: number | undefined;
};

const normalizeCompare = (value: string | undefined): string =>
  (value ?? "").trim().toLowerCase();

const exactMatches = (actual: string, expected: string | undefined): boolean =>
  expected === undefined || normalizeCompare(actual) === normalizeCompare(expected);

const nameMatches = (actual: string, expected: string | undefined): boolean =>
  expected === undefined || scoreBusinessNameMatch(expected, actual).matches;

const normalizeRows = (rows: readonly GeBIZRawRecord[]): readonly GeBIZNormalizedRecord[] =>
  rows.map((r) => ({
    agency: r.agency,
    tenderNo: r.tender_no,
    description: r.tender_description,
    awardDate: r.award_date,
    status: r.tender_detail_status,
    supplierName: r.supplier_name,
    awardedAmount: Number.isFinite(Number(r.awarded_amt)) ? Number(r.awarded_amt) : null,
    category: r.tender_category,
  }));

export const getGeBIZTenders = async (
  params: GeBIZFilterParams,
): Promise<readonly GeBIZNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.agency !== undefined) filters["agency"] = params.agency;
  if (params.category !== undefined) filters["tender_category"] = params.category;
  const limit = Math.min(params.limit ?? 50, 200);
  const rows = params.supplierName === undefined
    ? await queryDatastore<GeBIZRawRecord>(GEBIZ_RESOURCE_ID, {
        limit,
        sort: "award_date desc",
        filters,
      })
    : await queryDatastoreExactMatches<GeBIZRawRecord>(GEBIZ_RESOURCE_ID, {
        filters,
        matchLimit: limit,
        q: params.supplierName,
        pageSize: 100,
        exactMatch: (row) =>
          exactMatches(row.agency, params.agency)
          && exactMatches(row.tender_category, params.category)
          && nameMatches(row.supplier_name, params.supplierName),
      });

  return normalizeRows(rows);
};
