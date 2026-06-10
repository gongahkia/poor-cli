import type {
  PaCommunityOutletRecord,
  PaResidentNetworkCentreRecord,
} from "@swee-sg/shared";
import { downloadDatasetGeoJson } from "../datagov/client.js";
import {
  applyDirectoryFilters,
  buildAddress,
  normalizePostalCode,
  parseFmelTimestamp,
  toNullableString,
} from "../civic/utils.js";

const COMMUNITY_OUTLETS_DATASET_ID = "d_9de02d3fb33d96da1855f4fbef549a0f";
const RESIDENT_NETWORK_CENTRES_DATASET_ID = "d_9ae25d6b3fefdd15983c4e46ecc7fcbd";

const COMMUNITY_OUTLETS_SOURCE_URL = "https://data.gov.sg/datasets/d_9de02d3fb33d96da1855f4fbef549a0f/view";
const RESIDENT_NETWORK_CENTRES_SOURCE_URL = "https://data.gov.sg/datasets/d_9ae25d6b3fefdd15983c4e46ecc7fcbd/view";

type PaCommunityOutletFeature = {
  readonly geometry: {
    readonly coordinates?: readonly number[];
  };
  readonly properties: {
    readonly ADDRESSBLOCKHOUSENUMBER?: string | null;
    readonly ADDRESSSTREETNAME?: string | null;
    readonly ADDRESSPOSTALCODE?: string | null;
    readonly DESCRIPTION?: string | null;
    readonly HYPERLINK?: string | null;
    readonly NAME?: string | null;
    readonly FMEL_UPD_D?: string | number | null;
  };
};

type PaResidentNetworkFeature = {
  readonly geometry: {
    readonly coordinates?: readonly number[];
  };
  readonly properties: {
    readonly ADDRESSBLOCKHOUSENUMBER?: string | null;
    readonly ADDRESSSTREETNAME?: string | null;
    readonly ADDRESSPOSTALCODE?: string | null;
    readonly HYPERLINK?: string | null;
    readonly NAME?: string | null;
    readonly FMEL_UPD_D?: string | number | null;
  };
};

const toCommunityOutletType = (value: string | null | undefined): "community_club" | "passion_wave" => {
  return value?.trim().toUpperCase() === "PW" ? "passion_wave" : "community_club";
};

const normalizeCommunityOutlet = (
  feature: PaCommunityOutletFeature,
): PaCommunityOutletRecord => {
  const coordinates = feature.geometry.coordinates ?? [];
  const type = toCommunityOutletType(feature.properties.DESCRIPTION);
  return {
    name: feature.properties.NAME?.trim() ?? "Unknown outlet",
    category: "community",
    subcategory: type,
    address: buildAddress(
      feature.properties.ADDRESSBLOCKHOUSENUMBER,
      feature.properties.ADDRESSSTREETNAME,
    ),
    postalCode: normalizePostalCode(feature.properties.ADDRESSPOSTALCODE),
    lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
    lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
    sourceAgency: "People's Association",
    sourceDataset: "Community Club / PAssion WaVe Outlet",
    sourceUrl: COMMUNITY_OUTLETS_SOURCE_URL,
    lastUpdatedAt: parseFmelTimestamp(feature.properties.FMEL_UPD_D),
    type,
    url: toNullableString(feature.properties.HYPERLINK),
  };
};

const normalizeResidentNetworkCentre = (
  feature: PaResidentNetworkFeature,
): PaResidentNetworkCentreRecord => {
  const coordinates = feature.geometry.coordinates ?? [];
  return {
    name: feature.properties.NAME?.trim() ?? "Unknown residents' network centre",
    category: "community",
    subcategory: "resident_network_centre",
    address: buildAddress(
      feature.properties.ADDRESSBLOCKHOUSENUMBER,
      feature.properties.ADDRESSSTREETNAME,
    ),
    postalCode: normalizePostalCode(feature.properties.ADDRESSPOSTALCODE),
    lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
    lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
    sourceAgency: "People's Association",
    sourceDataset: "Residents' Committee / Residents' Network Centre",
    sourceUrl: RESIDENT_NETWORK_CENTRES_SOURCE_URL,
    lastUpdatedAt: parseFmelTimestamp(feature.properties.FMEL_UPD_D),
    url: toNullableString(feature.properties.HYPERLINK),
  };
};

export const getPaCommunityOutlets = async (
  params: Readonly<{
    name?: string | undefined;
    type?: "community_club" | "passion_wave" | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly PaCommunityOutletRecord[]> => {
  const collection = await downloadDatasetGeoJson<PaCommunityOutletFeature["properties"]>(
    COMMUNITY_OUTLETS_DATASET_ID,
    "STATIC",
  );
  const records = collection.features
    .map((feature) => normalizeCommunityOutlet(feature as unknown as PaCommunityOutletFeature))
    .filter((record) => params.type === undefined || record.type === params.type);

  return applyDirectoryFilters(records, params);
};

export const getPaResidentNetworkCentres = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly PaResidentNetworkCentreRecord[]> => {
  const collection = await downloadDatasetGeoJson<PaResidentNetworkFeature["properties"]>(
    RESIDENT_NETWORK_CENTRES_DATASET_ID,
    "STATIC",
  );
  const records = collection.features.map((feature) =>
    normalizeResidentNetworkCentre(feature as unknown as PaResidentNetworkFeature),
  );

  return applyDirectoryFilters(records, params);
};
