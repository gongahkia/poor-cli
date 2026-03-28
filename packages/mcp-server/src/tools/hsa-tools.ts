import {
  formatResponse,
  HsaHealthProductLicenseesBaseSchema,
  HsaHealthProductLicenseesSchema,
  HsaLicensedPharmaciesBaseSchema,
  HsaLicensedPharmaciesSchema,
  resolveOutputFormat,
  validateInput,
} from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../apis/hsa/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleHsaLicensedPharmacies = async (
  params: Readonly<{
    pharmacyName?: string | undefined;
    pharmacistInCharge?: string | undefined;
    pharmacyAddress?: string | undefined;
    postalCode?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getHsaLicensedPharmacies(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: { records: data },
  };
};

export const handleHsaHealthProductLicensees = async (
  params: Readonly<{
    companyName?: string | undefined;
    licenseType?: string | undefined;
    activityType?: string | undefined;
    dosageForm?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getHsaHealthProductLicensees(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: { records: data },
  };
};

export const hsaToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_hsa_licensed_pharmacies",
    description: "Look up HSA licensed pharmacies by exact pharmacy name, pharmacist in charge, address, or postal code.",
    surface: "canonical",
    inputSchema: HsaLicensedPharmaciesBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleHsaLicensedPharmacies(validateInput(HsaLicensedPharmaciesSchema, input)),
  },
  {
    name: "sg_hsa_health_product_licensees",
    description: "Look up HSA companies licensed to import, wholesale, or manufacture health products by exact company or licence filters.",
    surface: "canonical",
    inputSchema: HsaHealthProductLicenseesBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleHsaHealthProductLicensees(validateInput(HsaHealthProductLicenseesSchema, input)),
  },
];
