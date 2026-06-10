import { queryDatastore } from "../datagov/client.js";

// [Unverified] data.gov.sg EMA monthly electricity generation dataset resource id.
// Override via SG_API_EMA_GEN_RESOURCE_ID if upstream rotates.
const DEFAULT_EMA_GEN_RESOURCE_ID = "d_57ce66d52c3a50aabc9b4e6bcf8f2ec6";

const getEmaGenResourceId = (): string =>
  process.env["SG_API_EMA_GEN_RESOURCE_ID"]?.trim() || DEFAULT_EMA_GEN_RESOURCE_ID;

type EmaGenRawRecord = Readonly<{
  year?: string;
  month?: string;
  energy_product_type?: string;
  generation_gwh?: string;
}>;

export type EmaGenNormalizedRecord = {
  readonly year: string | null;
  readonly month: string | null;
  readonly energyType: string | null;
  readonly generationGwh: number | null;
};

export const getEmaElectricityGeneration = async (
  params: Readonly<{ energyType?: string | undefined; year?: string | undefined; limit?: number | undefined }>,
): Promise<readonly EmaGenNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.energyType !== undefined) filters["energy_product_type"] = params.energyType;
  if (params.year !== undefined) filters["year"] = params.year;
  const rows = await queryDatastore<EmaGenRawRecord>(getEmaGenResourceId(), {
    limit: Math.min(params.limit ?? 50, 200),
    sort: "year desc, month desc",
    filters,
  });
  return rows.map((r) => {
    const n = r.generation_gwh === undefined ? null : Number(r.generation_gwh);
    return {
      year: r.year ?? null,
      month: r.month ?? null,
      energyType: r.energy_product_type ?? null,
      generationGwh: n === null || !Number.isFinite(n) ? null : n,
    };
  });
};
