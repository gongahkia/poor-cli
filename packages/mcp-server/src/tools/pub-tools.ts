import { formatResponse, PubWaterLevelsSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
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
  description: "Get water level readings from PUB monitoring stations via data.gov.sg.",
  surface: "canonical",
  inputSchema: PubWaterLevelsSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handlePubWaterLevels(PubWaterLevelsSchema.parse(input)),
}];
