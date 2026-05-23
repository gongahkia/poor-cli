import { formatResponse, PubWaterLevelsSchema, resolveOutputFormat } from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { getWaterLevels } from "../apis/pub/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handlePubWaterLevels = async (
  params: Readonly<{ station?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getWaterLevels(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const pubToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_pub_water_levels",
  description: "Get PUB water-level sensor station records via data.gov.sg; public fields do not include live water-height readings.",
  surface: "canonical",
  inputSchema: PubWaterLevelsSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handlePubWaterLevels(PubWaterLevelsSchema.parse(input)),
}];
