export type BcaLicensedBuilderRecord = {
  readonly company_name: string;
  readonly uen_no: string;
  readonly class: string;
  readonly class_code: string;
  readonly additional_info: string;
  readonly expiry_date: string;
  readonly building_no: string;
  readonly street_name: string;
  readonly unit_no: string;
  readonly building_name: string;
  readonly postal_code: string;
  readonly tel_no: string;
};

export type BcaNormalizedLicensedBuilderRecord = {
  readonly companyName: string;
  readonly uenNo: string;
  readonly className: string;
  readonly classCode: string;
  readonly additionalInfo: string | null;
  readonly expiryDate: string;
  readonly buildingNo: string;
  readonly streetName: string;
  readonly unitNo: string | null;
  readonly buildingName: string | null;
  readonly postalCode: string;
  readonly telNo: string;
};

export type BcaRegisteredContractorRecord = {
  readonly company_name: string;
  readonly uen_no: string;
  readonly workhead: string;
  readonly grade: string;
  readonly additional_info: string;
  readonly expiry_date: string;
  readonly building_no: string;
  readonly street_name: string;
  readonly unit_no: string;
  readonly building_name: string;
  readonly postal_code: string;
  readonly tel_no: string;
};

export type BcaNormalizedRegisteredContractorRecord = {
  readonly companyName: string;
  readonly uenNo: string;
  readonly workhead: string;
  readonly grade: string;
  readonly additionalInfo: string | null;
  readonly expiryDate: string;
  readonly buildingNo: string | null;
  readonly streetName: string;
  readonly unitNo: string | null;
  readonly buildingName: string | null;
  readonly postalCode: string;
  readonly telNo: string;
};
