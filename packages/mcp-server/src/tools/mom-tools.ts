import { formatResponse, MomLabourStatsSchema, resolveOutputFormat } from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { getLabourStats } from "../apis/mom/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleMomLabourStats = async (
  params: Readonly<{ indicator?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getLabourStats(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const momToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_mom_labour_stats",
  description: "Get labour market statistics from MOM via data.gov.sg.",
  surface: "canonical",
  inputSchema: MomLabourStatsSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleMomLabourStats(MomLabourStatsSchema.parse(input)),
}];
