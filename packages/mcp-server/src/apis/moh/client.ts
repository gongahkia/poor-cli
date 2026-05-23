import { downloadDatasetGeoJson } from "../datagov/client.js";
import { normalizePostalCode, parseDescriptionAttributes, toNullableString } from "../civic/utils.js";

export const MOH_HEALTHCARE_FACILITIES_RESOURCE_ID = "d_548c33ea2d99e29ec63a7cc9edcccedc";

type FacilityFeature = {
  readonly geometry: {
    readonly coordinates?: readonly number[];
  };
  readonly properties: {
    readonly Description?: string;
  };
};

export type FacilityNormalizedRecord = {
  readonly name: string;
  readonly code: string;
  readonly type: string;
  readonly street: string;
  readonly block: string;
  readonly postalCode: string;
  readonly telephone: string;
  readonly lat?: number | null;
  readonly lng?: number | null;
};

type FacilityFilterParams = {
  readonly type?: string | undefined;
  readonly name?: string | undefined;
  readonly postalCode?: string | undefined;
  readonly limit?: number | undefined;
};

export const getHealthcareFacilities = async (
  params: FacilityFilterParams,
): Promise<readonly FacilityNormalizedRecord[]> => {
  const collection = await downloadDatasetGeoJson<FacilityFeature["properties"]>(
    MOH_HEALTHCARE_FACILITIES_RESOURCE_ID,
    "STATIC",
  );
  const normalizedType = params.type?.trim().toLowerCase();
  const normalizedName = params.name?.trim().toLowerCase();
  const normalizedPostalCode = normalizePostalCode(params.postalCode);
  return collection.features
    .map((feature) => {
      const geoFeature = feature as unknown as FacilityFeature;
      const attributes = parseDescriptionAttributes(geoFeature.properties.Description);
      const coordinates = geoFeature.geometry.coordinates ?? [];
      return {
        name: attributes["HCI_NAME"] ?? "Unknown healthcare facility",
        code: attributes["HCI_CODE"] ?? "",
        type: attributes["LICENCE_TYPE"] ?? "",
        street: attributes["STREET_NAME"] ?? "",
        block: attributes["BLK_HSE_NO"] ?? "",
        postalCode: normalizePostalCode(attributes["POSTAL_CD"]) ?? "",
        telephone: toNullableString(attributes["HCI_TEL"]) ?? "",
        lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
        lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
      };
    })
    .filter((record) => normalizedType === undefined || record.type.toLowerCase().includes(normalizedType))
    .filter((record) => normalizedName === undefined || record.name.toLowerCase().includes(normalizedName))
    .filter((record) => normalizedPostalCode === null || record.postalCode === normalizedPostalCode)
    .slice(0, Math.min(params.limit ?? 50, 200));
};
