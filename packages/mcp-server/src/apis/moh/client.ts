import { queryDatastore } from "../datagov/client.js";

const HOSPITALS_RESOURCE_ID = "d_23b6e552fdce728e1e9fa5a5103d0205";

type FacilityRawRecord = {
  readonly hci_name: string;
  readonly hci_code: string;
  readonly licence_type: string;
  readonly street_name: string;
  readonly building_blk_no: string;
  readonly postal_code: string;
  readonly tel_no: string;
};

export type FacilityNormalizedRecord = {
  readonly name: string;
  readonly code: string;
  readonly type: string;
  readonly street: string;
  readonly block: string;
  readonly postalCode: string;
  readonly telephone: string;
};

type FacilityFilterParams = {
  readonly type?: string;
  readonly name?: string;
  readonly postalCode?: string;
  readonly limit?: number;
};

export const getHealthcareFacilities = async (
  params: FacilityFilterParams,
): Promise<readonly FacilityNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.type !== undefined) filters["licence_type"] = params.type;
  if (params.name !== undefined) filters["hci_name"] = params.name;
  if (params.postalCode !== undefined) filters["postal_code"] = params.postalCode;
  const rows = await queryDatastore<FacilityRawRecord>(HOSPITALS_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    filters,
  });
  return rows.map((r) => ({
    name: r.hci_name,
    code: r.hci_code,
    type: r.licence_type,
    street: r.street_name,
    block: r.building_blk_no,
    postalCode: r.postal_code,
    telephone: r.tel_no,
  }));
};
