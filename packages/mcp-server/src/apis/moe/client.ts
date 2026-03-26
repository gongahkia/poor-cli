import { queryDatastore } from "../datagov/client.js";

const SCHOOLS_RESOURCE_ID = "d_688b934f82c1059ed0a6993d2a829089";

type SchoolRawRecord = {
  readonly school_name: string;
  readonly url_address: string;
  readonly address: string;
  readonly postal_code: string;
  readonly telephone_no: string;
  readonly mainlevel_code: string;
  readonly zone_code: string;
  readonly nature_code: string;
  readonly type_code: string;
};

export type SchoolNormalizedRecord = {
  readonly name: string;
  readonly url: string;
  readonly address: string;
  readonly postalCode: string;
  readonly telephone: string;
  readonly level: string;
  readonly zone: string;
  readonly nature: string;
  readonly type: string;
};

type SchoolFilterParams = {
  readonly level?: string;
  readonly zone?: string;
  readonly name?: string;
  readonly limit?: number;
};

export const getSchools = async (
  params: SchoolFilterParams,
): Promise<readonly SchoolNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.level !== undefined) filters["mainlevel_code"] = params.level.toUpperCase();
  if (params.zone !== undefined) filters["zone_code"] = params.zone.toUpperCase();
  if (params.name !== undefined) filters["school_name"] = params.name;
  const rows = await queryDatastore<SchoolRawRecord>(SCHOOLS_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    filters,
  });
  return rows.map((r) => ({
    name: r.school_name,
    url: r.url_address,
    address: r.address,
    postalCode: r.postal_code,
    telephone: r.telephone_no,
    level: r.mainlevel_code,
    zone: r.zone_code,
    nature: r.nature_code,
    type: r.type_code,
  }));
};
