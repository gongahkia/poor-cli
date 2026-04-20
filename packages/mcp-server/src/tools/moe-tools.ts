import { formatResponse, MoeSchoolsSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getSchools, MOE_SCHOOLS_RESOURCE_ID } from "../apis/moe/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const MOE_DIRECTORY_SOURCE_URL = "https://data.gov.sg/datasets/d_688b934f82c1059ed0a6993d2a829089/view";

export const handleMoeSchools = async (
  params: Readonly<{
    level?: string | undefined;
    zone?: string | undefined;
    name?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getSchools(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  const observedAt = new Date().toISOString();
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      provenance: {
        source: "data.gov.sg datastore",
        publisher: "Ministry of Education",
        dataset: "School Directory and Information",
        resourceId: MOE_SCHOOLS_RESOURCE_ID,
        datasetUrl: MOE_DIRECTORY_SOURCE_URL,
        license: "Singapore Open Data Licence v1.0",
      },
      freshness: {
        observedAt,
        sourceTimestamp: null,
      },
      limits: {
        defaultLimit: 50,
        maxLimit: 200,
        supportedFilters: ["level", "zone", "name"],
      },
    },
  };
};

export const moeToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_moe_schools",
    description: "Search Singapore schools from MOE directory via data.gov.sg, filtered by level, zone, or name.",
    surface: "canonical",
    inputSchema: MoeSchoolsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = MoeSchoolsSchema.parse(input);
      return handleMoeSchools(parsed);
    },
  },
];
