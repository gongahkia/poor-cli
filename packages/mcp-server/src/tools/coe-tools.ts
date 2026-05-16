import { formatResponse, LtaCoeResultsSchema, resolveOutputFormat } from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { getCoeBiddingResults } from "../apis/coe/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleLtaCoeResults = async (
  params: Readonly<{ category?: string | undefined; biddingNo?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getCoeBiddingResults(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const coeToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_lta_coe_results",
  description: "Get LTA Certificate of Entitlement (COE) bidding results (quota, bids, premium) by vehicle category and bidding exercise.",
  surface: "canonical",
  inputSchema: LtaCoeResultsSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleLtaCoeResults(LtaCoeResultsSchema.parse(input)),
}];
