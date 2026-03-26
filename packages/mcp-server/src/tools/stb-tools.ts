import { formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { z } from "zod";
import { getVisitorArrivals } from "../apis/stb/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const StbVisitorStatsSchema = z.object({
  country: z.string().min(1).optional(),
  year: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

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
