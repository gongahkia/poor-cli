import { formatResponse, resolveOutputFormat, SportSgFacilitiesSchema } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { toDirectoryGeoFeatures } from "../apis/civic/utils.js";
import { getSportSgFacilities } from "../apis/sportsg/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const renderDirectoryResult = (
  data: readonly Record<string, unknown>[],
  format: OutputFormat,
): string => {
  if (format === "geojson") {
    return formatResponse(toDirectoryGeoFeatures(data as never), "geojson");
  }
  return formatResponse(data, format);
};

export const handleSportSgFacilities = async (
  params: Readonly<{
    name?: string | undefined;
    facilityType?: string | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getSportSgFacilities(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: renderDirectoryResult(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const sportsgToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_sportsg_facilities",
    description: "Search Sport Singapore public facilities with optional facility-type, postal-code, or proximity filters.",
    surface: "canonical",
    inputSchema: SportSgFacilitiesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handleSportSgFacilities(SportSgFacilitiesSchema.parse(input)),
  },
];
