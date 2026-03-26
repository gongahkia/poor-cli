import { queryDatastore } from "../datagov/client.js";

const WATER_LEVEL_RESOURCE_ID = "d_133a1d14c0a848b7845c878249784a46";

type WaterLevelRawRecord = {
  readonly station: string;
  readonly reading_date: string;
  readonly reading_time: string;
  readonly water_level: string;
};

export type WaterLevelNormalizedRecord = {
  readonly station: string;
  readonly date: string;
  readonly time: string;
  readonly waterLevel: number | null;
};

export const getWaterLevels = async (
  params: { readonly station?: string; readonly limit?: number },
): Promise<readonly WaterLevelNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.station !== undefined) filters["station"] = params.station;
  const rows = await queryDatastore<WaterLevelRawRecord>(WATER_LEVEL_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    sort: "reading_date desc",
    filters,
  });
  return rows.map((r) => ({
    station: r.station,
    date: r.reading_date,
    time: r.reading_time,
    waterLevel: Number.isFinite(Number(r.water_level)) ? Number(r.water_level) : null,
  }));
};
