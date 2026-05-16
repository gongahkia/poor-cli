import { formatResponse, LawSearchSchema, resolveOutputFormat } from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { searchSingaporeLaw } from "../apis/law/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleLawSearch = async (
  params: Readonly<{ query: string; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await searchSingaporeLaw(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: {
      records: data,
      disclaimer: "Singapore Statutes Online results are for research only, not legal advice. Verify currency against the official source.",
      sourceUrl: "https://sso.agc.gov.sg/",
    },
  };
};

export const lawToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_law_search",
  description: "Search Singapore Statutes Online (sso.agc.gov.sg) for Acts and subsidiary legislation by keyword. Returns hit titles, URLs, and snippets only; no synthesis or legal advice.",
  surface: "canonical",
  inputSchema: LawSearchSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleLawSearch(LawSearchSchema.parse(input)),
}];
