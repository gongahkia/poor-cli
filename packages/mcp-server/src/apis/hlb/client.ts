import type { HlbHotelRecord } from "@swee-sg/shared";
import { downloadDatasetGeoJson } from "../datagov/client.js";
import { applyDirectoryFilters, normalizePostalCode, parseFmelTimestamp, toNullableString, toNumberOrNull } from "../civic/utils.js";
import { scoreBusinessNameMatch } from "../../diligence/name-matching.js";

const HLB_HOTELS_DATASET_ID = "d_654e22f14e5bb817423f0e0c9ac4f632";
const HLB_HOTELS_SOURCE_URL = "https://data.gov.sg/collections/140/view";

type HlbHotelFeature = {
  readonly geometry: {
    readonly coordinates?: readonly number[];
  };
  readonly properties: {
    readonly NAME?: string | null;
    readonly DESCRIPTION?: string | null;
    readonly POSTALCODE?: string | null;
    readonly KEEPERNAME?: string | null;
    readonly TOTALROOMS?: string | number | null;
    readonly HYPERLINK?: string | null;
    readonly INC_CRC?: string | null;
    readonly FMEL_UPD_D?: string | number | null;
  };
};

const nameMatches = (actual: string | null | undefined, expected: string | undefined): boolean =>
  expected === undefined || scoreBusinessNameMatch(expected, actual ?? "").matches;

const normalizeHotel = (feature: HlbHotelFeature): HlbHotelRecord => {
  const coordinates = feature.geometry.coordinates ?? [];
  return {
    name: feature.properties.NAME?.trim() ?? "Unknown hotel",
    category: "hospitality",
    subcategory: "hotel",
    address: feature.properties.DESCRIPTION?.trim() ?? "",
    postalCode: normalizePostalCode(feature.properties.POSTALCODE),
    lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
    lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
    sourceAgency: "Hotels Licensing Board",
    sourceDataset: "Hotels",
    sourceUrl: HLB_HOTELS_SOURCE_URL,
    lastUpdatedAt: parseFmelTimestamp(feature.properties.FMEL_UPD_D),
    keeperName: toNullableString(feature.properties.KEEPERNAME),
    totalRooms: toNumberOrNull(feature.properties.TOTALROOMS),
    url: toNullableString(feature.properties.HYPERLINK),
    incCrc: toNullableString(feature.properties.INC_CRC),
  };
};

export const getHlbHotels = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    keeperName?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly HlbHotelRecord[]> => {
  const collection = await downloadDatasetGeoJson<HlbHotelFeature["properties"]>(HLB_HOTELS_DATASET_ID, "DAILY");
  const records = collection.features
    .map((feature) => normalizeHotel(feature as unknown as HlbHotelFeature))
    .filter((record) =>
      nameMatches(record.keeperName, params.keeperName),
    );

  const directoryParams = {
    ...(params.postalCode === undefined ? {} : { postalCode: params.postalCode }),
    ...(params.lat === undefined ? {} : { lat: params.lat }),
    ...(params.lng === undefined ? {} : { lng: params.lng }),
    ...(params.radiusKm === undefined ? {} : { radiusKm: params.radiusKm }),
    ...(params.limit === undefined ? {} : { limit: params.limit }),
  };

  return applyDirectoryFilters(records, directoryParams)
    .filter((record) => nameMatches(record.name, params.name));
};
