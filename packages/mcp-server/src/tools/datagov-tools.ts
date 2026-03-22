import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, DatagovSearchSchema, DatagovGetSchema, DatagovBrowseSchema, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { searchDatasets, getDataset, listCollections } from "../apis/datagov/client.js";
import { registerTool } from "./registry.js";

export const handleDatagovSearch = async (
  params: Readonly<{ keyword: string; limit?: number | undefined }>,
): Promise<ToolResult> => {
  const results = await searchDatasets(params.keyword, params.limit);
  const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
  return { content: [{ type: "text", text }] };
};

export const registerDatagovTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_datagov_search",
    description: "Search data.gov.sg for datasets matching a keyword. Covers 2,000+ Singapore government datasets. Use this when no specific API covers the topic.",
    inputSchema: DatagovSearchSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleDatagovSearch(validateInput(DatagovSearchSchema, input));
    },
  });

  registerTool(server, {
    name: "sg_datagov_get",
    description: "Get metadata for a specific data.gov.sg dataset. Use sg_datagov_search first to find dataset IDs.",
    inputSchema: DatagovGetSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { datasetId, format } = validateInput(DatagovGetSchema, input);
      const result = await getDataset(datasetId);
      if (result === null) {
        return { content: [{ type: "text", text: "Dataset not found." }] };
      }
      const fmt = resolveOutputFormat(format);
      const text = formatResponse(result as unknown as Record<string, unknown>, fmt);
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_datagov_browse",
    description: "Browse data.gov.sg collections. Call without arguments to see all collections, or provide a collection name to see its datasets.",
    inputSchema: DatagovBrowseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { collection } = validateInput(DatagovBrowseSchema, input);
      if (collection !== undefined) {
        const results = await searchDatasets(collection, 20);
        const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
        return { content: [{ type: "text", text }] };
      }
      const collections = await listCollections();
      const text = formatResponse(collections as unknown as Record<string, unknown>[], "markdown");
      return { content: [{ type: "text", text }] };
    },
  });
};
