export type CivicDirectoryRecord = {
  readonly name: string;
  readonly category: string;
  readonly subcategory: string;
  readonly address: string;
  readonly postalCode: string | null;
  readonly lat: number | null;
  readonly lng: number | null;
  readonly sourceAgency: string;
  readonly sourceDataset: string;
  readonly sourceUrl: string;
  readonly lastUpdatedAt: string | null;
  readonly distanceKm?: number;
};

export type PaCommunityOutletRecord = CivicDirectoryRecord & {
  readonly type: "community_club" | "passion_wave";
  readonly url: string | null;
};

export type PaResidentNetworkCentreRecord = CivicDirectoryRecord & {
  readonly url: string | null;
};

export type SportSgFacilityType =
  | "sport_centre"
  | "swimming_complex"
  | "sports_hall"
  | "stadium"
  | "tennis_centre"
  | "squash_centre"
  | "hockey_centre"
  | "archery_centre"
  | "unknown";

export type SportSgFacilityRecord = CivicDirectoryRecord & {
  readonly facilityType: SportSgFacilityType;
  readonly detailsUrl: string | null;
};

export type EcdaVacancyStatus =
  | "available"
  | "limited"
  | "full"
  | "not_applicable"
  | "unknown";

export type EcdaChildcareCentreRecord = CivicDirectoryRecord & {
  readonly centreCode: string | null;
  readonly centreType: string | null;
  readonly operatorType: string | null;
  readonly serviceModel: string | null;
  readonly contactNo: string | null;
  readonly email: string | null;
  readonly website: string | null;
  readonly hasVacancy: boolean | null;
  readonly infantVacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly playgroupVacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly n1VacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly n2VacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly k1VacancyCurrentMonth: EcdaVacancyStatus | null;
  readonly k2VacancyCurrentMonth: EcdaVacancyStatus | null;
};

export type MsfFamilyServiceRecord = CivicDirectoryRecord & {
  readonly description: string | null;
  readonly telephone: string | null;
  readonly email: string | null;
  readonly url: string | null;
};

export type MsfStudentCareServiceRecord = CivicDirectoryRecord & {
  readonly auditStatus: string | null;
  readonly auditDate: string | null;
  readonly scfa: boolean | null;
  readonly businessProfile: string | null;
  readonly monthlyFee: number | null;
  readonly enrolment: number | null;
  readonly telephone: string | null;
  readonly email: string | null;
};

export type MsfSocialServiceOfficeRecord = CivicDirectoryRecord & {
  readonly description: string | null;
  readonly url: string | null;
};
