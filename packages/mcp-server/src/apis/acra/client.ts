import type {
  AcraEntityRecord,
  AcraNormalizedEntityRecord,
} from "@sg-apis/shared";
import { queryDatastoreExactMatches } from "../datagov/client.js";

const ACRA_SHARD_RESOURCE_IDS = {
  A: "d_8575e84912df3c28995b8e6e0e05205a",
  B: "d_3a3807c023c61ddfba947dc069eb53f2",
  C: "d_c0650f23e94c42e7a20921f4c5b75c24",
  D: "d_acbc938ec77af18f94cecc4a7c9ec720",
  E: "d_124a9bd407c7a25f8335b93b86e50fdd",
  F: "d_4526d47d6714d3b052eed4a30b8b1ed6",
  G: "d_b58303c68e9cf0d2ae93b73ffdbfbfa1",
  H: "d_fa2ed456cf2b8597bb7e064b08fc3c7c",
  I: "d_85518d970b8178975850457f60f1e738",
  J: "d_478f45a9c541cbe679ca55d1cd2b970b",
  K: "d_5573b0db0575db32190a2ad27919a7aa",
  L: "d_a2141adf93ec2a3c2ec2837b78d6d46e",
  M: "d_9af9317c646a1c881bb5591c91817cc6",
  N: "d_67e99e6eabc4aad9b5d48663b579746a",
  O: "d_5c4ef48b025fdfbc80056401f06e3df9",
  P: "d_181005ca270b45408b4cdfc954980ca2",
  Q: "d_4130f1d9d365d9f1633536e959f62bb7",
  R: "d_2b8c54b2a490d2fa36b925289e5d9572",
  S: "d_df7d2d661c0c11a7c367c9ee4bf896c1",
  T: "d_72f37e5c5d192951ddc5513c2b134482",
  U: "d_0cc5f52a1f298b916f317800251057f3",
  V: "d_e97e8e7fc55b85a38babf66b0fa46b73",
  W: "d_af2042c77ffaf0db5d75561ce9ef5688",
  X: "d_1cd970d8351b42be4a308d628a6dd9d3",
  Y: "d_31af23fdb79119ed185c256f03cb5773",
  Z: "d_4e3db8955fdcda6f9944097bef3d2724",
  OTHERS: "d_300ddc8da4e8f7bdc1bfc62d0d99e2e7",
} as const;

type AcraShardKey = keyof typeof ACRA_SHARD_RESOURCE_IDS;

const ACRA_SHARD_SEARCH_ORDER: readonly AcraShardKey[] = [
  "A",
  "B",
  "C",
  "D",
  "E",
  "F",
  "G",
  "H",
  "I",
  "J",
  "K",
  "L",
  "M",
  "N",
  "O",
  "P",
  "Q",
  "R",
  "S",
  "T",
  "U",
  "V",
  "W",
  "X",
  "Y",
  "Z",
  "OTHERS",
];

type AcraFilterParams = {
  readonly entityName?: string | undefined;
  readonly uen?: string | undefined;
  readonly limit?: number | undefined;
};

const normalizeFilter = (value: string | undefined): string | undefined => {
  const normalized = value?.trim();
  return normalized === "" ? undefined : normalized;
};

const normalizeCompare = (value: string): string => value.trim().toLowerCase();

const normalizeNullLike = (value: string): string | null => {
  const normalized = value.trim();
  if (normalized === "" || normalized.toLowerCase() === "na") {
    return null;
  }
  return normalized;
};

const exactMatches = (actual: string, expected: string | undefined): boolean => {
  return expected === undefined || normalizeCompare(actual) === normalizeCompare(expected);
};

const getQueryLimit = (limit?: number): number => Math.min(Math.max(limit ?? 10, 1), 50);

const getShardKeyForEntityName = (entityName: string): AcraShardKey => {
  const firstCharacter = entityName.trim().charAt(0).toUpperCase();
  if (/^[A-Z]$/.test(firstCharacter)) {
    return firstCharacter as AcraShardKey;
  }
  return "OTHERS";
};

const getResourceIdsForParams = (params: AcraFilterParams): readonly string[] => {
  const entityName = normalizeFilter(params.entityName);
  if (entityName !== undefined) {
    return [ACRA_SHARD_RESOURCE_IDS[getShardKeyForEntityName(entityName)]];
  }

  return ACRA_SHARD_SEARCH_ORDER.map((key) => ACRA_SHARD_RESOURCE_IDS[key]);
};

const buildDatastoreFilters = (params: AcraFilterParams): Readonly<Record<string, unknown>> => ({
  ...(params.entityName === undefined
    ? {}
    : { entity_name: { ilike: normalizeFilter(params.entityName)! } }),
  ...(params.uen === undefined
    ? {}
    : { uen: normalizeFilter(params.uen)!.toUpperCase() }),
});

export const getAcraEntities = async (
  params: AcraFilterParams,
): Promise<readonly AcraNormalizedEntityRecord[]> => {
  const matchLimit = getQueryLimit(params.limit);
  const resourceIds = getResourceIdsForParams(params);
  const matches: AcraEntityRecord[] = [];

  for (const resourceId of resourceIds) {
    if (matches.length >= matchLimit) {
      break;
    }

    const rows = await queryDatastoreExactMatches<AcraEntityRecord>(resourceId, {
      matchLimit: matchLimit - matches.length,
      filters: buildDatastoreFilters(params),
      sort: "entity_name asc",
      exactMatch: (row) =>
        exactMatches(row.entity_name, params.entityName)
        && exactMatches(row.uen, params.uen),
    });

    matches.push(...rows);
  }

  return matches.map((row) => ({
    uen: row.uen,
    issuanceAgencyId: row.issuance_agency_id,
    entityName: row.entity_name,
    entityTypeDescription: row.entity_type_description,
    businessConstitutionDescription: normalizeNullLike(row.business_constitution_description),
    companyTypeDescription: normalizeNullLike(row.company_type_description),
    pafConstitutionDescription: normalizeNullLike(row.paf_constitution_description),
    entityStatusDescription: row.entity_status_description,
    registrationIncorporationDate: row.registration_incorporation_date,
    uenIssueDate: row.uen_issue_date,
    addressType: row.address_type,
    block: normalizeNullLike(row.block),
    streetName: normalizeNullLike(row.street_name),
    levelNo: normalizeNullLike(row.level_no),
    unitNo: normalizeNullLike(row.unit_no),
    buildingName: normalizeNullLike(row.building_name),
    postalCode: normalizeNullLike(row.postal_code),
    otherAddressLine1: normalizeNullLike(row.other_address_line1),
    otherAddressLine2: normalizeNullLike(row.other_address_line2),
    accountDueDate: normalizeNullLike(row.account_due_date),
    annualReturnDate: normalizeNullLike(row.annual_return_date),
    primarySsicCode: row.primary_ssic_code,
    primarySsicDescription: normalizeNullLike(row.primary_ssic_description),
    primaryUserDescribedActivity: normalizeNullLike(row.primary_user_described_activity),
    secondarySsicCode: normalizeNullLike(row.secondary_ssic_code),
    secondarySsicDescription: normalizeNullLike(row.secondary_ssic_description),
    secondaryUserDescribedActivity: normalizeNullLike(row.secondary_user_described_activity),
    noOfOfficers: Number.isFinite(Number(row.no_of_officers)) ? Number(row.no_of_officers) : null,
  }));
};
