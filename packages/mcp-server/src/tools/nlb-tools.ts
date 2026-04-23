import { formatResponse, NlbLibrariesSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getNlbLibraries } from "../apis/nlb/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleNlbLibraries = async (
  params: Readonly<{ name?: string | undefined; region?: string | undefined; postalCode?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getNlbLibraries(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const nlbToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_nlb_libraries",
  description: "Search NLB public library directory by name, region, or postal code via data.gov.sg.",
  surface: "canonical",
  inputSchema: NlbLibrariesSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleNlbLibraries(NlbLibrariesSchema.parse(input)),
}];
