import type { EcdaChildcareCentreRecord, EcdaVacancyStatus } from "@swee-sg/shared";
import { downloadDatasetCsvRows, downloadDatasetGeoJson } from "../datagov/client.js";
import {
  applyDirectoryFilters,
  normalizeLookupKey,
  normalizePostalCode,
  normalizeVacancyStatus,
  parseFmelTimestamp,
  toNullableString,
} from "../civic/utils.js";

const CHILDCARE_GEOJSON_DATASET_ID = "d_5d668e3f544335f8028f546827b773b4";
const CHILDCARE_LISTING_DATASET_ID = "d_696c994c50745b079b3684f0e90ffc53";

const CHILDCARE_SOURCE_URL = "https://data.gov.sg/datasets/d_5d668e3f544335f8028f546827b773b4/view";

type ChildcareGeoFeature = {
  readonly geometry: {
    readonly coordinates?: readonly number[];
  };
  readonly properties: {
    readonly ADDRESSPOSTALCODE?: string | null;
    readonly ADDRESSSTREETNAME?: string | null;
    readonly NAME?: string | null;
    readonly FMEL_UPD_D?: string | number | null;
  };
};

type ChildcareListingRow = Readonly<Record<string, string>>;

const getVacancyStatuses = (row: ChildcareListingRow | null): {
  readonly infantVacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly playgroupVacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly n1VacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly n2VacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly k1VacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly k2VacancyCurrentMonth: EcdaVacancyStatus | null;
} => ({
  infantVacancyCurrentMonth: normalizeVacancyStatus(row?.["infant_vacancy_current_month"]),
  playgroupVacancyCurrentMonth: normalizeVacancyStatus(row?.["pg_vacancy_current_month"]),
  n1VacancyCurrentMonth: normalizeVacancyStatus(row?.["n1_vacancy_current_month"]),
  n2VacancyCurrentMonth: normalizeVacancyStatus(row?.["n2_vacancy_current_month"]),
  k1VacancyCurrentMonth: normalizeVacancyStatus(row?.["k1_vacancy_current_month"]),
  k2VacancyCurrentMonth: normalizeVacancyStatus(row?.["k2_vacancy_current_month"]),
});

const vacancyStatuses = (
  row: ChildcareListingRow | null,
): readonly EcdaVacancyStatus[] => {
  const statuses = getVacancyStatuses(row);
  return Object.values(statuses).filter((value): value is EcdaVacancyStatus => value !== null);
};

const deriveHasVacancy = (row: ChildcareListingRow | null): boolean | null => {
  if (row === null) return null;
  const statuses = vacancyStatuses(row);
  if (statuses.length === 0) return null;
  return statuses.some((status) => status === "available" || status === "limited");
};

const buildListingIndexes = (rows: readonly ChildcareListingRow[]) => {
  const byPostalCode = new Map<string, ChildcareListingRow>();
  const byName = new Map<string, ChildcareListingRow>();

  for (const row of rows) {
    const postalCode = normalizePostalCode(row["postal_code"]);
    if (postalCode !== null && !byPostalCode.has(postalCode)) {
      byPostalCode.set(postalCode, row);
    }

    const normalizedName = normalizeLookupKey(row["centre_name"]);
    if (normalizedName !== "" && !byName.has(normalizedName)) {
      byName.set(normalizedName, row);
    }
  }

  return { byPostalCode, byName };
};

const inferCentreType = (row: ChildcareListingRow | null): string | null => {
  const typeCode = toNullableString(row?.["tp_code"]);
  if (typeCode !== null) {
    return typeCode.toUpperCase();
  }

  const serviceModel = (row?.["service_model"] ?? "").toLowerCase();
  if (serviceModel.includes("kindergarten")) return "KN";
  if (serviceModel.includes("child care") || serviceModel.includes("childcare")) return "CC";
  return null;
};

const normalizeChildcareCentre = (
  feature: ChildcareGeoFeature,
  listingRow: ChildcareListingRow | null,
): EcdaChildcareCentreRecord => {
  const coordinates = feature.geometry.coordinates ?? [];
  const statuses = getVacancyStatuses(listingRow);
  const geoPostalCode = normalizePostalCode(feature.properties.ADDRESSPOSTALCODE);
  const listingPostalCode = normalizePostalCode(listingRow?.["postal_code"]);
  const centreType = inferCentreType(listingRow);
  return {
    name: feature.properties.NAME?.trim() ?? listingRow?.["centre_name"] ?? "Unknown childcare centre",
    category: "childcare",
    subcategory: listingRow?.["service_model"]?.trim().toLowerCase() || "childcare_centre",
    address: listingRow?.["centre_address"]?.trim()
      || feature.properties.ADDRESSSTREETNAME?.trim()
      || "",
    postalCode: geoPostalCode ?? listingPostalCode,
    lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
    lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
    sourceAgency: "Early Childhood Development Agency",
    sourceDataset: "Child Care Services + Listing of Centres",
    sourceUrl: CHILDCARE_SOURCE_URL,
    lastUpdatedAt: listingRow?.["last_updated"]?.trim() || parseFmelTimestamp(feature.properties.FMEL_UPD_D),
    centreCode: toNullableString(listingRow?.["centre_code"]),
    centreType,
    operatorType: toNullableString(listingRow?.["organisation_description"]),
    serviceModel: toNullableString(listingRow?.["service_model"]),
    contactNo: toNullableString(listingRow?.["centre_contact_no"] ?? listingRow?.["contactno_lifesg"]),
    email: toNullableString(listingRow?.["centre_email_address"] ?? listingRow?.["emailaddress_lifesg"]),
    website: toNullableString(listingRow?.["centre_website"] ?? listingRow?.["website_lifesg"]),
    hasVacancy: deriveHasVacancy(listingRow),
    ...statuses,
  };
};

export const getEcdaChildcareCentres = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    centreType?: string | undefined;
    operatorType?: string | undefined;
    hasVacancy?: boolean | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly EcdaChildcareCentreRecord[]> => {
  const [geojson, listingRows] = await Promise.all([
    downloadDatasetGeoJson<ChildcareGeoFeature["properties"]>(CHILDCARE_GEOJSON_DATASET_ID, "DAILY"),
    downloadDatasetCsvRows<ChildcareListingRow>(CHILDCARE_LISTING_DATASET_ID, "DAILY"),
  ]);

  const indexes = buildListingIndexes(listingRows);
  const normalizedCentreType = params.centreType?.trim().toUpperCase();
  const normalizedOperatorType = params.operatorType?.trim().toLowerCase();

  const records = geojson.features
    .map((feature) => {
      const geoFeature = feature as unknown as ChildcareGeoFeature;
      const postalCode = normalizePostalCode(geoFeature.properties.ADDRESSPOSTALCODE);
      const nameKey = normalizeLookupKey(geoFeature.properties.NAME);
      const listingRow = (postalCode !== null ? indexes.byPostalCode.get(postalCode) : undefined)
        ?? indexes.byName.get(nameKey)
        ?? null;
      return normalizeChildcareCentre(geoFeature, listingRow);
    })
    .filter((record) =>
      normalizedCentreType === undefined || record.centreType?.toUpperCase() === normalizedCentreType,
    )
    .filter((record) =>
      normalizedOperatorType === undefined
      || (record.operatorType?.toLowerCase().includes(normalizedOperatorType) ?? false),
    )
    .filter((record) =>
      params.hasVacancy === undefined
      || record.hasVacancy === params.hasVacancy,
    );

  return applyDirectoryFilters(records, params);
};
