import { formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { z } from "zod";
import { getLabourStats } from "../apis/mom/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const MomLabourStatsSchema = z.object({
  indicator: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const handleMomLabourStats = async (
  params: Readonly<{ indicator?: string; limit?: number; format?: OutputFormat }>,
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
