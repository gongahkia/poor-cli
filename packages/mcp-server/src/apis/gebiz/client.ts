import { queryDatastore } from "../datagov/client.js";

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
  readonly agency?: string;
  readonly category?: string;
  readonly supplierName?: string;
  readonly limit?: number;
};

export const getGeBIZTenders = async (
  params: GeBIZFilterParams,
): Promise<readonly GeBIZNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.agency !== undefined) filters["agency"] = params.agency;
  if (params.category !== undefined) filters["tender_category"] = params.category;
  if (params.supplierName !== undefined) filters["supplier_name"] = params.supplierName;
  const rows = await queryDatastore<GeBIZRawRecord>(GEBIZ_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    sort: "award_date desc",
    filters,
  });
  return rows.map((r) => ({
    agency: r.agency,
    tenderNo: r.tender_no,
    description: r.tender_description,
    awardDate: r.award_date,
    status: r.tender_detail_status,
    supplierName: r.supplier_name,
    awardedAmount: Number.isFinite(Number(r.awarded_amt)) ? Number(r.awarded_amt) : null,
    category: r.tender_category,
  }));
};
