import { formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { z } from "zod";
import { getParks } from "../apis/nparks/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const NParksSchema = z.object({
  name: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const handleNParks = async (
  params: Readonly<{ name?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getParks(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const nparksToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_nparks_parks",
  description: "List parks and nature reserves from NParks via data.gov.sg.",
  surface: "canonical",
  inputSchema: NParksSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleNParks(NParksSchema.parse(input)),
}];
