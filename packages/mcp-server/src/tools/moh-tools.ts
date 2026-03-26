import { formatResponse, MohFacilitiesSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getHealthcareFacilities } from "../apis/moh/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleMohFacilities = async (
  params: Readonly<{
    type?: string | undefined;
    name?: string | undefined;
    postalCode?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getHealthcareFacilities(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return { content: [{ type: "text", text }], structuredContent: { records: data } };
};

export const mohToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_moh_facilities",
    description: "Search healthcare facilities (hospitals, clinics) from MOH directory via data.gov.sg.",
    surface: "canonical",
    inputSchema: MohFacilitiesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = MohFacilitiesSchema.parse(input);
      return handleMohFacilities(parsed);
    },
  },
];
