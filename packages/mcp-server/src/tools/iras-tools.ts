import { formatResponse, IrasTaxCollectionSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getIrasTaxCollection } from "../apis/iras/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleIrasTaxCollection = async (
  params: Readonly<{ financialYear?: string | undefined; taxType?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getIrasTaxCollection(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const irasToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_iras_tax_collection",
  description: "Get IRAS annual tax collection records by financial year and tax type via data.gov.sg.",
  surface: "canonical",
  inputSchema: IrasTaxCollectionSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleIrasTaxCollection(IrasTaxCollectionSchema.parse(input)),
}];
