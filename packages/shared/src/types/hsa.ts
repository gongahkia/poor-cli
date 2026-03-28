export type HsaLicensedPharmacyRecord = {
  readonly pharmacy_name: string;
  readonly pharmacist_in_charge: string;
  readonly pharmacy_address: string;
};

export type HsaNormalizedLicensedPharmacyRecord = {
  readonly pharmacyName: string;
  readonly pharmacistInCharge: string | null;
  readonly pharmacyAddress: string;
  readonly postalCode: string | null;
};

export type HsaHealthProductLicenseeRecord = {
  readonly company_name: string;
  readonly license_type: string;
  readonly activity_type: string;
  readonly dosage_form: string;
  readonly expiry_date: string;
};

export type HsaNormalizedHealthProductLicenseeRecord = {
  readonly companyName: string;
  readonly licenseType: string;
  readonly activityType: string | null;
  readonly dosageForm: string | null;
  readonly expiryDate: string | null;
};
