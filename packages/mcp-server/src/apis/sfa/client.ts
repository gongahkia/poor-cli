import { queryDatastore } from "../datagov/client.js";

const LICENSED_EATING_RESOURCE_ID = "d_26781731d47d6eab5fba5b8adf498baf";

type SfaRawRecord = {
  readonly business_name: string;
  readonly licence_number: string;
  readonly address: string;
  readonly licence_type: string;
};

export type SfaNormalizedRecord = {
  readonly businessName: string;
  readonly licenceNumber: string;
  readonly address: string;
  readonly licenceType: string;
};

export const getSfaEstablishments = async (
  params: { readonly name?: string; readonly limit?: number },
): Promise<readonly SfaNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.name !== undefined) filters["business_name"] = params.name;
  const rows = await queryDatastore<SfaRawRecord>(LICENSED_EATING_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    filters,
  });
  return rows.map((r) => ({
    businessName: r.business_name,
    licenceNumber: r.licence_number,
    address: r.address,
    licenceType: r.licence_type,
  }));
};
