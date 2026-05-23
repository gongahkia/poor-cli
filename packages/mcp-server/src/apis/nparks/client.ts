import { downloadDatasetGeoJson } from "../datagov/client.js";
import { parseFmelTimestamp } from "../civic/utils.js";

const PARKS_DATASET_ID = "d_77d7ec97be83d44f61b85454f844382f";
const PARKS_SOURCE_URL = "https://data.gov.sg/datasets/d_77d7ec97be83d44f61b85454f844382f/view";

type ParkFeature = {
  readonly NAME?: string | null;
  readonly N_RESERVE?: number | string | null;
  readonly FMEL_UPD_D?: string | number | null;
};

export type ParkNormalizedRecord = {
  readonly name: string;
  readonly description: string;
  readonly url: string;
  readonly lastUpdatedAt: string | null;
};

export const getParks = async (
  params: { readonly name?: string | undefined; readonly limit?: number | undefined },
): Promise<readonly ParkNormalizedRecord[]> => {
  const collection = await downloadDatasetGeoJson<ParkFeature>(PARKS_DATASET_ID, "STATIC");
  const needle = params.name?.trim().toLowerCase();
  return collection.features
    .map((feature) => {
      const name = feature.properties.NAME?.trim() || "Unknown park";
      const reserveFlag = String(feature.properties.N_RESERVE ?? "").trim();
      return {
        name,
        description: reserveFlag === "1" ? "Nature reserve or nature-area polygon." : "Park or open-space polygon.",
        url: PARKS_SOURCE_URL,
        lastUpdatedAt: parseFmelTimestamp(feature.properties.FMEL_UPD_D),
      };
    })
    .filter((record) => needle === undefined || record.name.toLowerCase().includes(needle))
    .slice(0, Math.min(params.limit ?? 50, 200));
};
