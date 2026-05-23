import { formatResponse, MohFacilitiesSchema, resolveOutputFormat } from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { getHealthcareFacilities, MOH_HEALTHCARE_FACILITIES_RESOURCE_ID } from "../apis/moh/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const MOH_DIRECTORY_SOURCE_URL = "https://data.gov.sg/datasets/d_548c33ea2d99e29ec63a7cc9edcccedc/view";

export const handleMohFacilities = async (
  params: Readonly<{
    type?: string | undefined;
    name?: string | undefined;
    postalCode?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getHealthcareFacilities(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  const observedAt = new Date().toISOString();
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      provenance: {
        source: "data.gov.sg datastore",
        publisher: "Ministry of Health",
        dataset: "CHAS Clinics",
        resourceId: MOH_HEALTHCARE_FACILITIES_RESOURCE_ID,
        datasetUrl: MOH_DIRECTORY_SOURCE_URL,
        license: "Singapore Open Data Licence v1.0",
      },
      freshness: {
        observedAt,
        sourceTimestamp: null,
      },
      limits: {
        defaultLimit: 50,
        maxLimit: 200,
        supportedFilters: ["type", "name", "postalCode"],
      },
    },
  };
};

export const mohToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_moh_facilities",
    description: "Search CHAS clinic facility records from MOH via data.gov.sg. Directory coverage only; does not provide medical advice.",
    surface: "canonical",
    inputSchema: MohFacilitiesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = MohFacilitiesSchema.parse(input);
      return handleMohFacilities(parsed);
    },
  },
];
