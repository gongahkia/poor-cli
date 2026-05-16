import type {
  HsaHealthProductLicenseeRecord,
  HsaLicensedPharmacyRecord,
  HsaNormalizedHealthProductLicenseeRecord,
  HsaNormalizedLicensedPharmacyRecord,
} from "@dude/shared";
import { downloadDatasetCsvRows } from "../datagov/client.js";
import { normalizePostalCode, toNullableString } from "../civic/utils.js";

const HSA_LICENSED_PHARMACIES_DATASET_ID = "d_bc50d72a9d61457964c6ea8d8ba7dce2";
const HSA_HEALTH_PRODUCT_LICENSEES_DATASET_ID = "d_bf50ce0f3f42f69d7acd50635afa62da";

const normalizeCompare = (value: string | undefined): string => {
  return (value ?? "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
};

const exactMatches = (actual: string, expected: string | undefined): boolean => {
  return expected === undefined || normalizeCompare(actual) === normalizeCompare(expected);
};

const extractPostalCode = (address: string): string | null => {
  const embedded = address.match(/SG\((\d{6})\)/i)?.[1]
    ?? address.match(/\b(\d{6})\b/)?.[1];
  return normalizePostalCode(embedded);
};

const getLimit = (value: number | undefined): number => Math.min(Math.max(value ?? 50, 1), 100);

export const getHsaLicensedPharmacies = async (
  params: Readonly<{
    pharmacyName?: string | undefined;
    pharmacistInCharge?: string | undefined;
    pharmacyAddress?: string | undefined;
    postalCode?: string | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly HsaNormalizedLicensedPharmacyRecord[]> => {
  const rows = await downloadDatasetCsvRows<HsaLicensedPharmacyRecord>(HSA_LICENSED_PHARMACIES_DATASET_ID, "DAILY");
  return rows
    .filter((row) => {
      const postalCode = extractPostalCode(row.pharmacy_address);
      return exactMatches(row.pharmacy_name, params.pharmacyName)
        && exactMatches(row.pharmacist_in_charge, params.pharmacistInCharge)
        && exactMatches(row.pharmacy_address, params.pharmacyAddress)
        && (params.postalCode === undefined || postalCode === normalizePostalCode(params.postalCode));
    })
    .map((row) => ({
      pharmacyName: row.pharmacy_name.trim(),
      pharmacistInCharge: toNullableString(row.pharmacist_in_charge),
      pharmacyAddress: row.pharmacy_address.trim(),
      postalCode: extractPostalCode(row.pharmacy_address),
    }))
    .sort((left, right) => left.pharmacyName.localeCompare(right.pharmacyName))
    .slice(0, getLimit(params.limit));
};

export const getHsaHealthProductLicensees = async (
  params: Readonly<{
    companyName?: string | undefined;
    licenseType?: string | undefined;
    activityType?: string | undefined;
    dosageForm?: string | undefined;
    limit?: number | undefined;
  }>,
): Promise<readonly HsaNormalizedHealthProductLicenseeRecord[]> => {
  const rows = await downloadDatasetCsvRows<HsaHealthProductLicenseeRecord>(HSA_HEALTH_PRODUCT_LICENSEES_DATASET_ID, "DAILY");
  return rows
    .filter((row) =>
      exactMatches(row.company_name, params.companyName)
      && exactMatches(row.license_type, params.licenseType)
      && exactMatches(row.activity_type, params.activityType)
      && exactMatches(row.dosage_form, params.dosageForm),
    )
    .map((row) => ({
      companyName: row.company_name.trim(),
      licenseType: row.license_type.trim(),
      activityType: toNullableString(row.activity_type),
      dosageForm: toNullableString(row.dosage_form),
      expiryDate: toNullableString(row.expiry_date),
    }))
    .sort((left, right) => left.companyName.localeCompare(right.companyName))
    .slice(0, getLimit(params.limit));
};
