import { formatResponse, SpfCrimeStatsSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getSpfCrimeStats } from "../apis/spf/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleSpfCrimeStats = async (
  params: Readonly<{ offenceCategory?: string | undefined; year?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getSpfCrimeStats(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const spfToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_spf_crime_stats",
  description: "Get Singapore Police Force annual crime statistics by offence category and year via data.gov.sg.",
  surface: "canonical",
  inputSchema: SpfCrimeStatsSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleSpfCrimeStats(SpfCrimeStatsSchema.parse(input)),
}];
