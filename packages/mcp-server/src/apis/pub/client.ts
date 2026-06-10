import { downloadDatasetXlsxRows } from "../datagov/client.js";

const WATER_LEVEL_SENSORS_DATASET_ID = "d_31333fa5cf0834f012d840365b336610";
const WATER_LEVEL_SENSORS_SOURCE_URL = "https://data.gov.sg/datasets/d_31333fa5cf0834f012d840365b336610/view";

type WaterLevelSensorRow = Readonly<{
  readonly "Station ID"?: string;
  readonly "Station Name"?: string;
  readonly X?: string;
  readonly Y?: string;
}>;

type WaterLevelSensorRecord = {
  readonly station: string;
  readonly stationId: string | null;
  readonly easting: number | null;
  readonly northing: number | null;
};

export type WaterLevelNormalizedRecord = {
  readonly station: string;
  readonly stationId: string | null;
  readonly date: string | null;
  readonly time: string | null;
  readonly waterLevel: number | null;
  readonly lat: number | null;
  readonly lng: number | null;
  readonly easting: number | null;
  readonly northing: number | null;
  readonly url: string | null;
  readonly lastUpdatedAt: string | null;
};

const toNumberOrNull = (value: string | undefined): number | null => {
  if (value === undefined || value.trim() === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const normalizeSensorRow = (row: WaterLevelSensorRow): WaterLevelSensorRecord => ({
  station: row["Station Name"]?.trim() || "Unknown PUB water-level sensor",
  stationId: row["Station ID"]?.trim() || null,
  easting: toNumberOrNull(row.X),
  northing: toNumberOrNull(row.Y),
});

export const getWaterLevels = async (
  params: { readonly station?: string | undefined; readonly limit?: number | undefined },
): Promise<readonly WaterLevelNormalizedRecord[]> => {
  const rows = await downloadDatasetXlsxRows<WaterLevelSensorRow>(WATER_LEVEL_SENSORS_DATASET_ID, "STATIC");
  const needle = params.station?.trim().toLowerCase();
  return rows
    .map(normalizeSensorRow)
    .filter((record) => needle === undefined || record.station.toLowerCase().includes(needle))
    .map((record) => ({
      ...record,
      date: null,
      time: null,
      waterLevel: null,
      lat: null,
      lng: null,
      url: WATER_LEVEL_SENSORS_SOURCE_URL,
      lastUpdatedAt: null,
    }))
    .slice(0, Math.min(params.limit ?? 50, 200));
};
