import { formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { z } from "zod";
import { getHealthcareFacilities } from "../apis/moh/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const MohFacilitiesSchema = z.object({
  type: z.string().min(1).optional().describe("Hospital, Medical Clinic, Dental Clinic, etc."),
  name: z.string().min(1).optional(),
  postalCode: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const handleMohFacilities = async (
  params: Readonly<{
    type?: string;
    name?: string;
    postalCode?: string;
    limit?: number;
    format?: OutputFormat;
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
