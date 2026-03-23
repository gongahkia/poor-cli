import { validateInput, DatagovSearchSchema, DatagovGetSchema, DatagovBrowseSchema, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { searchDatasets, getDataset, listCollections } from "../apis/datagov/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleDatagovSearch = async (
  params: Readonly<{ keyword: string; limit?: number | undefined }>,
): Promise<ToolResult> => {
  const results = await searchDatasets(params.keyword, params.limit);
  const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: results,
    },
  };
};

export const handleDatagovGet = async (
  params: Readonly<{ datasetId: string; format?: "json" | "markdown" | "csv" | "geojson" | undefined }>,
): Promise<ToolResult> => {
  const result = await getDataset(params.datasetId);
  if (result === null) {
    return { content: [{ type: "text", text: "Dataset not found." }] };
  }
  const fmt = resolveOutputFormat(params.format);
  const text = formatResponse(result as unknown as Record<string, unknown>, fmt);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      record: result,
    },
  };
};

export const handleDatagovBrowse = async (
  params: Readonly<{ collection?: string | undefined }>,
): Promise<ToolResult> => {
  if (params.collection !== undefined) {
    const results = await searchDatasets(params.collection, 20);
    const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
    return {
      content: [{ type: "text", text }],
      structuredContent: {
        records: results,
      },
    };
  }
  const collections = await listCollections();
  const text = formatResponse(collections as unknown as Record<string, unknown>[], "markdown");
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: collections,
    },
  };
};

export const datagovToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_datagov_search",
    description: "Search data.gov.sg for datasets matching a keyword. Covers 2,000+ Singapore government datasets. Use this when no specific API covers the topic.",
    surface: "canonical",
    inputSchema: DatagovSearchSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleDatagovSearch(validateInput(DatagovSearchSchema, input));
    },
  },

  {
    name: "sg_datagov_get",
    description: "Get metadata for a specific data.gov.sg dataset. Use sg_datagov_search first to find dataset IDs.",
    surface: "canonical",
    scopeNotes: ["Metadata only."],
    inputSchema: DatagovGetSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleDatagovGet(validateInput(DatagovGetSchema, input));
    },
  },

  {
    name: "sg_datagov_browse",
    description: "Browse data.gov.sg collections. Call without arguments to see all collections, or provide a collection name to see its datasets.",
    surface: "canonical",
    inputSchema: DatagovBrowseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleDatagovBrowse(validateInput(DatagovBrowseSchema, input));
    },
  },
];
