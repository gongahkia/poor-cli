import { formatResponse, SfaEstablishmentsSchema, resolveOutputFormat } from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { getSfaEstablishments } from "../apis/sfa/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleSfaEstablishments = async (
  params: Readonly<{ name?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getSfaEstablishments(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const sfaToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_sfa_establishments",
  description: "Search SFA licensed food establishments via data.gov.sg.",
  surface: "canonical",
  inputSchema: SfaEstablishmentsSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleSfaEstablishments(SfaEstablishmentsSchema.parse(input)),
}];
