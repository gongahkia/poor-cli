import { queryDatastore } from "../datagov/client.js";

const LABOUR_RESOURCE_ID = "d_56b0e0b9c1d94b8c8c95ba0a91b95e9d";

type LabourRawRecord = {
  readonly indicator: string;
  readonly year: string;
  readonly value: string;
};

export type LabourNormalizedRecord = {
  readonly indicator: string;
  readonly year: string;
  readonly value: number | null;
};

export const getLabourStats = async (
  params: { readonly indicator?: string; readonly limit?: number },
): Promise<readonly LabourNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.indicator !== undefined) filters["indicator"] = params.indicator;
  const rows = await queryDatastore<LabourRawRecord>(LABOUR_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    sort: "year desc",
    filters,
  });
  return rows.map((r) => ({
    indicator: r.indicator,
    year: r.year,
    value: Number.isFinite(Number(r.value)) ? Number(r.value) : null,
  }));
};
