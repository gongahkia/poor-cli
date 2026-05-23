import { ApiError } from "@swee-sg/shared";
import { downloadDatasetGeoJson, getDatasetMetadata } from "../datagov/client.js";
import { parseDescriptionAttributes, parseFmelTimestamp, toNullableString } from "../civic/utils.js";

const WATER_LEVEL_SENSORS_DATASET_ID = "d_31333fa5cf0834f012d840365b336610";

type WaterLevelSensorFeature = {
  readonly Description?: string;
};

export type WaterLevelNormalizedRecord = {
  readonly station: string;
  readonly stationId: string | null;
  readonly date: string | null;
  readonly time: string | null;
  readonly waterLevel: number | null;
  readonly lat: number | null;
  readonly lng: number | null;
  readonly url: string | null;
  readonly lastUpdatedAt: string | null;
};

export const getWaterLevels = async (
  params: { readonly station?: string | undefined; readonly limit?: number | undefined },
): Promise<readonly WaterLevelNormalizedRecord[]> => {
  const metadata = await getDatasetMetadata(WATER_LEVEL_SENSORS_DATASET_ID);
  if (metadata?.format.toUpperCase() !== "GEOJSON") {
    throw new ApiError({
      apiName: "datagov",
      source: "data.gov.sg",
      statusCode: 422,
      code: "UNSUPPORTED_SOURCE_FORMAT",
      message: "data.gov.sg currently exposes PUB Water Level Sensors as a non-GeoJSON download, so sg_pub_water_levels reports a source gap instead of inferring live water-height values.",
      retryable: false,
      suggestedAction: "Inspect the PUB dataset on data.gov.sg or add a parser for the current published file format before treating this source as ready.",
    });
  }

  const collection = await downloadDatasetGeoJson<WaterLevelSensorFeature>(WATER_LEVEL_SENSORS_DATASET_ID, "STATIC");
  const needle = params.station?.trim().toLowerCase();
  return collection.features
    .map((feature) => {
      const attributes = parseDescriptionAttributes(feature.properties.Description);
      const coordinates = feature.geometry.coordinates ?? [];
      return {
        station: attributes["STATION_NAME"] ?? "Unknown PUB water-level sensor",
        stationId: toNullableString(attributes["STATION_ID"]),
        date: null,
        time: null,
        waterLevel: null,
        lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
        lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
        url: toNullableString(attributes["HYPERLINK"]),
        lastUpdatedAt: parseFmelTimestamp(attributes["FMEL_UPD_D"]),
      };
    })
    .filter((record) => needle === undefined || record.station.toLowerCase().includes(needle))
    .slice(0, Math.min(params.limit ?? 50, 200));
};
