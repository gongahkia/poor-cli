import type { SportSgFacilityRecord, SportSgFacilityType } from "@swee-sg/shared";
import { downloadDatasetGeoJson } from "../datagov/client.js";
import {
  applyDirectoryFilters,
  buildAddress,
  normalizePostalCode,
  parseFmelTimestamp,
  toNullableString,
} from "../civic/utils.js";

const SPORTSG_DATASET_ID = "d_9b87bab59d036a60fad2a91530e10773";
const SPORTSG_SOURCE_URL = "https://data.gov.sg/datasets/d_9b87bab59d036a60fad2a91530e10773/view";

type SportSgFeature = {
  readonly geometry: {
    readonly coordinates?: readonly number[];
  };
  readonly properties: {
    readonly VENUE?: string | null;
    readonly ADDRESSBLOCKHOUSENUMBER?: string | null;
    readonly ADDRESSSTREETNAME?: string | null;
    readonly POSTAL_CODE?: string | null;
    readonly DETAILS?: string | null;
    readonly FMEL_UPD_D?: string | number | null;
  };
};

const inferFacilityType = (venue: string): SportSgFacilityType => {
  const lower = venue.toLowerCase();
  if (lower.includes("swimming")) return "swimming_complex";
  if (lower.includes("tennis")) return "tennis_centre";
  if (lower.includes("squash")) return "squash_centre";
  if (lower.includes("stadium")) return "stadium";
  if (lower.includes("sports hall")) return "sports_hall";
  if (lower.includes("hockey")) return "hockey_centre";
  if (lower.includes("archery")) return "archery_centre";
  if (lower.includes("sport centre")) return "sport_centre";
  return "unknown";
};

const normalizeSportSgFacility = (feature: SportSgFeature): SportSgFacilityRecord => {
  const coordinates = feature.geometry.coordinates ?? [];
  const name = feature.properties.VENUE?.trim() ?? "Unknown SportSG facility";
  const facilityType = inferFacilityType(name);
  return {
    name,
    category: "sports",
    subcategory: facilityType,
    address: buildAddress(
      feature.properties.ADDRESSBLOCKHOUSENUMBER,
      feature.properties.ADDRESSSTREETNAME,
    ),
    postalCode: normalizePostalCode(feature.properties.POSTAL_CODE),
    lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
    lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
    sourceAgency: "Sport Singapore",
    sourceDataset: "SportSG Sport Facilities (GEOJSON)",
    sourceUrl: SPORTSG_SOURCE_URL,
    lastUpdatedAt: parseFmelTimestamp(feature.properties.FMEL_UPD_D),
    facilityType,
    detailsUrl: toNullableString(feature.properties.DETAILS),
  };
};

export const getSportSgFacilities = async (
  params: Readonly<{
    name?: string | undefined;
    facilityType?: string | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly SportSgFacilityRecord[]> => {
  const collection = await downloadDatasetGeoJson<SportSgFeature["properties"]>(
    SPORTSG_DATASET_ID,
    "STATIC",
  );
  const normalizedFacilityType = params.facilityType?.trim().toLowerCase();
  const records = collection.features
    .map((feature) => normalizeSportSgFacility(feature as unknown as SportSgFeature))
    .filter((record) =>
      normalizedFacilityType === undefined
      || record.facilityType === normalizedFacilityType
      || record.subcategory === normalizedFacilityType,
    );

  return applyDirectoryFilters(records, params);
};
