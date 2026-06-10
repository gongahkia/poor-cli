import type {
  MsfFamilyServiceRecord,
  MsfSocialServiceOfficeRecord,
  MsfStudentCareServiceRecord,
} from "@swee-sg/shared";
import { downloadDatasetGeoJson } from "../datagov/client.js";
import {
  applyDirectoryFilters,
  buildAddress,
  normalizePostalCode,
  parseFmelTimestamp,
  toNullableString,
  toNumberOrNull,
} from "../civic/utils.js";

const FAMILY_SERVICES_DATASET_ID = "d_add23c06f7267e799185c79ccaa2099b";
const STUDENT_CARE_SERVICES_DATASET_ID = "d_77e6e0d58ce4743dab1f26dfcbbeb6f4";
const SOCIAL_SERVICE_OFFICES_DATASET_ID = "d_22cfe2aed0bf20a679ab59bcaf0f8248";

const FAMILY_SERVICES_SOURCE_URL = "https://data.gov.sg/datasets/d_add23c06f7267e799185c79ccaa2099b/view";
const STUDENT_CARE_SERVICES_SOURCE_URL = "https://data.gov.sg/datasets/d_77e6e0d58ce4743dab1f26dfcbbeb6f4/view";
const SOCIAL_SERVICE_OFFICES_SOURCE_URL = "https://data.gov.sg/datasets/d_22cfe2aed0bf20a679ab59bcaf0f8248/view";

type MsfGeoFeature<TProperties extends Record<string, unknown>> = {
  readonly geometry: {
    readonly coordinates?: readonly number[];
  };
  readonly properties: TProperties;
};

type FamilyServiceProperties = {
  readonly ADDRESSBLOCKHOUSENUMBER?: string | null;
  readonly ADDRESSBUILDINGNAME?: string | null;
  readonly ADDRESSFLOORNUMBER?: string | null;
  readonly ADDRESSPOSTALCODE?: string | null;
  readonly ADDRESSSTREETNAME?: string | null;
  readonly ADDRESSUNITNUMBER?: string | null;
  readonly DESCRIPTION?: string | null;
  readonly EMAIL?: string | null;
  readonly FMEL_UPD_D?: string | number | null;
  readonly HYPERLINK?: string | null;
  readonly NAME?: string | null;
  readonly TELEPHONE?: string | null;
};

type StudentCareProperties = {
  readonly AUDIT_DATE?: string | null;
  readonly AUDIT_STATUS?: string | null;
  readonly BUSINESS_PROFILE?: string | null;
  readonly ENROLMENT?: string | number | null;
  readonly FMEL_UPD_D?: string | number | null;
  readonly MONTHLY_FEE?: string | number | null;
  readonly NAME_OF_STUDENT_CARE_CENTRE?: string | null;
  readonly SCC_ADDRESS?: string | null;
  readonly SCC_EMAIL?: string | null;
  readonly SCC_POSTAL_CODE?: string | null;
  readonly SCC_TELEPHONE?: string | null;
  readonly SCFA_Y_N?: string | null;
};

type SocialServiceOfficeProperties = {
  readonly BLOCKHOUSENUMBER?: string | null;
  readonly BUILDINGNAME?: string | null;
  readonly DESCRIPTION?: string | null;
  readonly FLOORNUMBER?: string | null;
  readonly FMEL_UPD_D?: string | number | null;
  readonly HYPERLINK?: string | null;
  readonly NAME?: string | null;
  readonly POSTALCODE?: string | null;
  readonly STREETNAME?: string | null;
  readonly UNITNUMBER?: string | null;
};

const toCoordinates = (
  feature: MsfGeoFeature<Record<string, unknown>>,
): { lat: number | null; lng: number | null } => {
  const coordinates = feature.geometry.coordinates ?? [];
  return {
    lat: typeof coordinates[1] === "number" ? coordinates[1] : null,
    lng: typeof coordinates[0] === "number" ? coordinates[0] : null,
  };
};

const normalizeAddressFragment = (value: string | null): string | null => {
  const normalized = toNullableString(value);
  return normalized === null ? null : normalized.replace(/\s+/g, " ").trim();
};

const toUnitPart = (
  floorNumber: string | null,
  unitNumber: string | null,
): string | null => {
  const normalizedFloor = normalizeAddressFragment(floorNumber);
  const normalizedUnit = normalizeAddressFragment(unitNumber);

  if (normalizedFloor !== null && normalizedUnit !== null) {
    if (normalizedFloor.includes("-")) {
      return `${normalizedFloor}${normalizedUnit.replace(/^#/, "")}`;
    }
    if (normalizedFloor.startsWith("#")) {
      return `${normalizedFloor}-${normalizedUnit.replace(/^#/, "")}`;
    }
    return `#${normalizedFloor}-${normalizedUnit.replace(/^#/, "")}`;
  }

  if (normalizedFloor !== null) {
    return normalizedFloor.startsWith("#") ? normalizedFloor : `#${normalizedFloor}`;
  }

  if (normalizedUnit !== null) {
    return normalizedUnit.startsWith("#") ? normalizedUnit : `Unit ${normalizedUnit}`;
  }

  return null;
};

const parseCompactDate = (value: string | null | undefined): string | null => {
  const normalized = toNullableString(value);
  if (normalized === null) {
    return null;
  }
  if (/^\d{8}$/.test(normalized)) {
    return `${normalized.slice(0, 4)}-${normalized.slice(4, 6)}-${normalized.slice(6, 8)}`;
  }
  return normalized;
};

const buildStructuredAddress = (
  streetAddress: string | null,
  buildingName: string | null,
  block: string | null,
  streetName: string | null,
  floorNumber: string | null,
  unitNumber: string | null,
): string => {
  if (streetAddress !== null) {
    return buildAddress(streetAddress, buildingName);
  }

  const unitPart = toUnitPart(floorNumber, unitNumber);

  return buildAddress(block, streetName, unitPart, buildingName);
};

const toNumberFromCurrency = (value: string | number | null | undefined): number | null => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value !== "string") {
    return null;
  }
  return toNumberOrNull(value.replace(/[^0-9.-]/g, ""));
};

const normalizeFamilyService = (
  feature: MsfGeoFeature<FamilyServiceProperties>,
): MsfFamilyServiceRecord => {
  const { lat, lng } = toCoordinates(feature as MsfGeoFeature<Record<string, unknown>>);
  const streetAddress = toNullableString(feature.properties.ADDRESSSTREETNAME);
  return {
    name: feature.properties.NAME?.trim() ?? "Unknown family service centre",
    category: "social_support",
    subcategory: "family_service_centre",
    address: buildStructuredAddress(
      streetAddress,
      toNullableString(feature.properties.ADDRESSBUILDINGNAME),
      toNullableString(feature.properties.ADDRESSBLOCKHOUSENUMBER),
      null,
      toNullableString(feature.properties.ADDRESSFLOORNUMBER),
      toNullableString(feature.properties.ADDRESSUNITNUMBER),
    ),
    postalCode: normalizePostalCode(feature.properties.ADDRESSPOSTALCODE),
    lat,
    lng,
    sourceAgency: "Ministry of Social and Family Development",
    sourceDataset: "Family Services",
    sourceUrl: FAMILY_SERVICES_SOURCE_URL,
    lastUpdatedAt: parseFmelTimestamp(feature.properties.FMEL_UPD_D),
    description: toNullableString(feature.properties.DESCRIPTION),
    telephone: toNullableString(feature.properties.TELEPHONE),
    email: toNullableString(feature.properties.EMAIL),
    url: toNullableString(feature.properties.HYPERLINK),
  };
};

const normalizeStudentCare = (
  feature: MsfGeoFeature<StudentCareProperties>,
): MsfStudentCareServiceRecord => {
  const { lat, lng } = toCoordinates(feature as MsfGeoFeature<Record<string, unknown>>);
  return {
    name: feature.properties.NAME_OF_STUDENT_CARE_CENTRE?.trim() ?? "Unknown student care centre",
    category: "childcare",
    subcategory: "student_care",
    address: feature.properties.SCC_ADDRESS?.trim() ?? "",
    postalCode: normalizePostalCode(feature.properties.SCC_POSTAL_CODE),
    lat,
    lng,
    sourceAgency: "Ministry of Social and Family Development",
    sourceDataset: "Student Care Services",
    sourceUrl: STUDENT_CARE_SERVICES_SOURCE_URL,
    lastUpdatedAt: parseFmelTimestamp(feature.properties.FMEL_UPD_D),
    auditStatus: toNullableString(feature.properties.AUDIT_STATUS),
    auditDate: parseCompactDate(feature.properties.AUDIT_DATE),
    scfa: feature.properties.SCFA_Y_N?.trim().toUpperCase() === "Y"
      ? true
      : feature.properties.SCFA_Y_N?.trim().toUpperCase() === "N"
        ? false
        : null,
    businessProfile: toNullableString(feature.properties.BUSINESS_PROFILE),
    monthlyFee: toNumberFromCurrency(feature.properties.MONTHLY_FEE),
    enrolment: toNumberOrNull(feature.properties.ENROLMENT),
    telephone: toNullableString(feature.properties.SCC_TELEPHONE),
    email: toNullableString(feature.properties.SCC_EMAIL),
  };
};

const normalizeSocialServiceOffice = (
  feature: MsfGeoFeature<SocialServiceOfficeProperties>,
): MsfSocialServiceOfficeRecord => {
  const { lat, lng } = toCoordinates(feature as MsfGeoFeature<Record<string, unknown>>);
  return {
    name: feature.properties.NAME?.trim() ?? "Unknown social service office",
    category: "social_support",
    subcategory: "social_service_office",
    address: buildStructuredAddress(
      null,
      toNullableString(feature.properties.BUILDINGNAME),
      toNullableString(feature.properties.BLOCKHOUSENUMBER),
      toNullableString(feature.properties.STREETNAME),
      toNullableString(feature.properties.FLOORNUMBER),
      toNullableString(feature.properties.UNITNUMBER),
    ),
    postalCode: normalizePostalCode(feature.properties.POSTALCODE),
    lat,
    lng,
    sourceAgency: "Ministry of Social and Family Development",
    sourceDataset: "Social Service Offices",
    sourceUrl: SOCIAL_SERVICE_OFFICES_SOURCE_URL,
    lastUpdatedAt: parseFmelTimestamp(feature.properties.FMEL_UPD_D),
    description: toNullableString(feature.properties.DESCRIPTION),
    url: toNullableString(feature.properties.HYPERLINK),
  };
};

export const getMsfFamilyServices = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly MsfFamilyServiceRecord[]> => {
  const collection = await downloadDatasetGeoJson<FamilyServiceProperties>(
    FAMILY_SERVICES_DATASET_ID,
    "STATIC",
  );

  const records = collection.features.map((feature) =>
    normalizeFamilyService(feature as unknown as MsfGeoFeature<FamilyServiceProperties>),
  );

  return applyDirectoryFilters(records, params);
};

export const getMsfStudentCareServices = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    auditStatus?: string | undefined;
    scfaOnly?: boolean | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly MsfStudentCareServiceRecord[]> => {
  const collection = await downloadDatasetGeoJson<StudentCareProperties>(
    STUDENT_CARE_SERVICES_DATASET_ID,
    "STATIC",
  );
  const normalizedAuditStatus = params.auditStatus?.trim().toLowerCase();
  const records = collection.features
    .map((feature) => normalizeStudentCare(feature as unknown as MsfGeoFeature<StudentCareProperties>))
    .filter((record) =>
      normalizedAuditStatus === undefined
      || (record.auditStatus?.toLowerCase().includes(normalizedAuditStatus) ?? false),
    )
    .filter((record) => params.scfaOnly !== true || record.scfa === true);

  return applyDirectoryFilters(records, params);
};

export const getMsfSocialServiceOffices = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly MsfSocialServiceOfficeRecord[]> => {
  const collection = await downloadDatasetGeoJson<SocialServiceOfficeProperties>(
    SOCIAL_SERVICE_OFFICES_DATASET_ID,
    "STATIC",
  );
  const records = collection.features.map((feature) =>
    normalizeSocialServiceOffice(feature as unknown as MsfGeoFeature<SocialServiceOfficeProperties>),
  );

  return applyDirectoryFilters(records, params);
};
