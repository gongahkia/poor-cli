import { formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { z } from "zod";
import { getSfaEstablishments } from "../apis/sfa/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const SfaEstablishmentsSchema = z.object({
  name: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const handleSfaEstablishments = async (
  params: Readonly<{ name?: string; limit?: number; format?: OutputFormat }>,
): Promise<ToolResult> => {
  const data = await getSfaEstablishments(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const sfaToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_sfa_establishments",
  description: "Search SFA licensed food establishments via data.gov.sg.",
  surface: "canonical",
  inputSchema: SfaEstablishmentsSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleSfaEstablishments(SfaEstablishmentsSchema.parse(input)),
}];
