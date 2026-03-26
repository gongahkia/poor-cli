import { formatResponse, StbVisitorStatsSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getVisitorArrivals } from "../apis/stb/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleStbVisitorStats = async (
  params: Readonly<{ country?: string | undefined; year?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getVisitorArrivals(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const stbToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_stb_visitor_stats",
  description: "Get Singapore visitor arrival statistics from STB via data.gov.sg.",
  surface: "canonical",
  inputSchema: StbVisitorStatsSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleStbVisitorStats(StbVisitorStatsSchema.parse(input)),
}];
