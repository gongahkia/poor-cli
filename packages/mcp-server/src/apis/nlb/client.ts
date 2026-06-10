import { downloadDatasetGeoJson } from "../datagov/client.js";
import {
  buildAddress,
  normalizePostalCode,
  parseDescriptionAttributes,
  parseFmelTimestamp,
  toNullableString,
} from "../civic/utils.js";

// data.gov.sg NLB Libraries dataset id.
// Override via SG_API_NLB_LIBRARIES_RESOURCE_ID if upstream rotates.
const DEFAULT_NLB_LIBRARIES_RESOURCE_ID = "d_27b8dae65d9ca1539e14d09578b17cbf";

const getNlbLibrariesResourceId = (): string =>
  process.env["SG_API_NLB_LIBRARIES_RESOURCE_ID"]?.trim() || DEFAULT_NLB_LIBRARIES_RESOURCE_ID;

type NlbLibraryFeature = Readonly<{
  Description?: string;
}>;

export type NlbLibraryRecord = {
  readonly name: string | null;
  readonly address: string | null;
  readonly postalCode: string | null;
  readonly region: string | null;
  readonly telephone: string | null;
  readonly lat: number | null;
  readonly lng: number | null;
  readonly url: string | null;
  readonly lastUpdatedAt: string | null;
};

export const getNlbLibraries = async (
  params: Readonly<{ name?: string | undefined; region?: string | undefined; postalCode?: string | undefined; limit?: number | undefined }>,
): Promise<readonly NlbLibraryRecord[]> => {
  const collection = await downloadDatasetGeoJson<NlbLibraryFeature>(getNlbLibrariesResourceId(), "STATIC");
  const needle = params.name?.trim().toLowerCase();
  const postalCode = normalizePostalCode(params.postalCode);
  const region = params.region?.trim().toLowerCase();
  const records = collection.features.map((feature) => {
    const attributes = parseDescriptionAttributes(feature.properties.Description);
    const coordinates = feature.geometry.coordinates ?? [];
    const name = toNullableString(attributes["NAME"]);
    return {
      name,
      address: buildAddress(
        attributes["ADDRESSBLOCKHOUSENUMBER"],
        attributes["ADDRESSBUILDINGNAME"],
        attributes["ADDRESSSTREETNAME"],
        attributes["ADDRESSFLOORNUMBER"] === undefined ? undefined : `#${attributes["ADDRESSFLOORNUMBER"]}`,
        attributes["ADDRESSUNITNUMBER"],
      ) || null,
      postalCode: normalizePostalCode(attributes["ADDRESSPOSTALCODE"]),
      region: null,
      telephone: null,
      lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
      lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
      url: toNullableString(attributes["HYPERLINK"]),
      lastUpdatedAt: parseFmelTimestamp(attributes["FMEL_UPD_D"]),
    } satisfies NlbLibraryRecord;
  });

  return records
    .filter((record) => needle === undefined || (record.name ?? "").toLowerCase().includes(needle))
    .filter((record) => postalCode === null || record.postalCode === postalCode)
    .filter((record) => region === undefined || (record.region ?? "").toLowerCase() === region)
    .slice(0, Math.min(params.limit ?? 50, 200));
};
