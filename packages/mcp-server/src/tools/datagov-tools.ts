import {
  validateInput,
  DatagovSearchSchema,
  DatagovGetSchema,
  DatagovResourcesSchema,
  DatagovRowsBaseSchema,
  DatagovRowsSchema,
  DatagovBrowseSchema,
  formatResponse,
  resolveOutputFormat,
} from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import {
  searchDatasets,
  getDataset,
  getDatasetResources,
  getDatasetRows,
  listCollections,
} from "../apis/datagov/client.js";
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

export const handleDatagovResources = async (
  params: Readonly<{ datasetId: string; format?: "json" | "markdown" | "csv" | "geojson" | undefined }>,
): Promise<ToolResult> => {
  const result = await getDatasetResources(params.datasetId);
  if (result === null) {
    return { content: [{ type: "text", text: "Dataset not found." }] };
  }

  const fmt = resolveOutputFormat(params.format);
  const resourceRows = result.resources.map((resource) => ({
    resourceId: resource.resourceId,
    format: resource.format,
    machineReadable: resource.machineReadable,
    columns: resource.columns.length,
  }));
  const columns = result.resources.flatMap((resource) =>
    resource.columns.map((column) => ({
      resourceId: resource.resourceId,
      name: column.name,
      title: column.title,
      dataType: column.dataType,
      isCategorical: column.isCategorical,
    })),
  );

  const text = fmt === "markdown"
    ? [
        `## ${result.name}`,
        "",
        formatResponse([{
          datasetId: result.datasetId,
          format: result.format,
          managedByAgencyName: result.managedByAgencyName,
          lastUpdatedAt: result.lastUpdatedAt,
          resourceCount: result.resources.length,
        }], "markdown"),
        "",
        "### Resources",
        formatResponse(resourceRows as Record<string, unknown>[], "markdown"),
        "",
        "### Columns",
        formatResponse(columns as Record<string, unknown>[], "markdown"),
      ].join("\n")
    : formatResponse(result as unknown as Record<string, unknown>, fmt);

  return {
    content: [{ type: "text", text }],
    structuredContent: {
      record: result,
    },
  };
};

export const handleDatagovRows = async (
  params: Readonly<{
    datasetId?: string | undefined;
    resourceId?: string | undefined;
    filters?: Readonly<Record<string, unknown>> | undefined;
    limit?: number | undefined;
    offset?: number | undefined;
    sort?: string | undefined;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
  }>,
): Promise<ToolResult> => {
  const result = await getDatasetRows({
    ...(params.datasetId === undefined ? {} : { datasetId: params.datasetId }),
    ...(params.resourceId === undefined ? {} : { resourceId: params.resourceId }),
    ...(params.filters === undefined ? {} : { filters: params.filters }),
    ...(params.limit === undefined ? {} : { limit: params.limit }),
    ...(params.offset === undefined ? {} : { offset: params.offset }),
    ...(params.sort === undefined ? {} : { sort: params.sort }),
  });
  const fmt = resolveOutputFormat(params.format);
  const text = fmt === "markdown"
    ? [
        `## ${result.datasetName ?? result.resourceId}`,
        "",
        formatResponse([{
          datasetId: result.datasetId ?? null,
          resourceId: result.resourceId,
          total: result.total,
          offset: result.offset,
          limit: result.limit,
          returned: result.records.length,
        }], "markdown"),
        "",
        formatResponse(result.records as Record<string, unknown>[], "markdown"),
      ].join("\n")
    : fmt === "json"
      ? formatResponse(result as unknown as Record<string, unknown>, "json")
      : formatResponse(result.records as unknown as Record<string, unknown>[], fmt);

  return {
    content: [{ type: "text", text }],
    structuredContent: {
      ...(result.datasetId === undefined ? {} : { datasetId: result.datasetId }),
      ...(result.datasetName === undefined ? {} : { datasetName: result.datasetName }),
      resourceId: result.resourceId,
      total: result.total,
      offset: result.offset,
      limit: result.limit,
      fields: result.fields,
      records: result.records,
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
    name: "sg_datagov_resources",
    description: "Inspect the machine-readable resource metadata for one data.gov.sg dataset, including the current resource ID and column metadata.",
    surface: "canonical",
    scopeNotes: ["Uses the current v2 metadata contract and exposes the dataset's current tabular resource shape."],
    inputSchema: DatagovResourcesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleDatagovResources(validateInput(DatagovResourcesSchema, input));
    },
  },
  {
    name: "sg_datagov_rows",
    description: "Read bounded rows from one data.gov.sg datastore resource with explicit filters, pagination, and sort options.",
    surface: "canonical",
    scopeNotes: ["Requires datasetId or resourceId.", "Returns truthful pagination metadata with the row payload."],
    inputSchema: DatagovRowsBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleDatagovRows(validateInput(DatagovRowsSchema, input));
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
