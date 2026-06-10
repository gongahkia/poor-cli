import { queryDatastore } from "../datagov/client.js";

// [Unverified] data.gov.sg IRAS annual tax collection dataset resource id.
// Override via SG_API_IRAS_TAX_RESOURCE_ID if upstream rotates.
const DEFAULT_IRAS_TAX_RESOURCE_ID = "d_829ea09697f1d6bc29cb2e1bcf2a90a9";

const getIrasTaxResourceId = (): string =>
  process.env["SG_API_IRAS_TAX_RESOURCE_ID"]?.trim() || DEFAULT_IRAS_TAX_RESOURCE_ID;

type IrasTaxRawRecord = Readonly<{
  financial_year?: string;
  tax_type?: string;
  revenue_source?: string;
  tax_collection?: string;
}>;

export type IrasTaxNormalizedRecord = {
  readonly financialYear: string | null;
  readonly taxType: string | null;
  readonly revenueSource: string | null;
  readonly taxCollection: number | null;
};

export const getIrasTaxCollection = async (
  params: Readonly<{ financialYear?: string | undefined; taxType?: string | undefined; limit?: number | undefined }>,
): Promise<readonly IrasTaxNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.financialYear !== undefined) filters["financial_year"] = params.financialYear;
  if (params.taxType !== undefined) filters["tax_type"] = params.taxType;
  const rows = await queryDatastore<IrasTaxRawRecord>(getIrasTaxResourceId(), {
    limit: Math.min(params.limit ?? 50, 200),
    sort: "financial_year desc",
    filters,
  });
  return rows.map((r) => {
    const n = r.tax_collection === undefined ? null : Number(r.tax_collection);
    return {
      financialYear: r.financial_year ?? null,
      taxType: r.tax_type ?? null,
      revenueSource: r.revenue_source ?? null,
      taxCollection: n === null || !Number.isFinite(n) ? null : n,
    };
  });
};
