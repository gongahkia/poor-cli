import {
  formatResponse,
  HlbHotelsInputSchema,
  HlbHotelsSchema,
  resolveOutputFormat,
} from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { toDirectoryGeoFeatures } from "../apis/civic/utils.js";
import { getHlbHotels } from "../apis/hlb/client.js";
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

export const handleHlbHotels = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    keeperName?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getHlbHotels(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: renderDirectoryResult(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const hlbToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_hlb_hotels",
    description: "Search HLB-licensed hotels by name, keeper name, postal code, or proximity.",
    surface: "canonical",
    inputSchema: HlbHotelsInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleHlbHotels(HlbHotelsSchema.parse(input)),
  },
];
