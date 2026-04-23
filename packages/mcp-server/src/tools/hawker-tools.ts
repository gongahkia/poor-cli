import { formatResponse, HawkerCentresInputSchema, HawkerCentresSchema, HawkerClosuresSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getHawkerCentres } from "../apis/hawker/client.js";
import { getHawkerClosures } from "../apis/hawker/closures-client.js";
import { toDirectoryGeoFeatures } from "../apis/civic/utils.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleHawkerCentres = async (
  params: Readonly<{
    name?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getHawkerCentres(params);
  const format = resolveOutputFormat(params.format);
  const text = format === "geojson"
    ? formatResponse(toDirectoryGeoFeatures(data as never), "geojson")
    : formatResponse(data as unknown as Record<string, unknown>[], format);
  return { content: [{ type: "text", text }], structuredContent: { records: data } };
};

export const handleHawkerClosures = async (
  params: Readonly<{ centre?: string | undefined; startDate?: string | undefined; endDate?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getHawkerClosures(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const hawkerToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_hawker_centres",
    description: "Search hawker centres in Singapore with optional proximity filtering by coordinates and radius.",
    surface: "canonical",
    inputSchema: HawkerCentresInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = HawkerCentresSchema.parse(input);
      return handleHawkerCentres(parsed);
    },
  },
  {
    name: "sg_hawker_closures",
    description: "Get hawker centre quarterly cleaning and other-works closure windows, optionally filtered to a centre or date range.",
    surface: "canonical",
    inputSchema: HawkerClosuresSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handleHawkerClosures(HawkerClosuresSchema.parse(input)),
  },
];
