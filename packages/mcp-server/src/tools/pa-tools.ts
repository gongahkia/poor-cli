import {
  formatResponse,
  PaCommunityOutletsInputSchema,
  PaCommunityOutletsSchema,
  PaResidentNetworkCentresInputSchema,
  PaResidentNetworkCentresSchema,
  resolveOutputFormat,
} from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { getPaCommunityOutlets, getPaResidentNetworkCentres } from "../apis/pa/client.js";
import { toDirectoryGeoFeatures } from "../apis/civic/utils.js";
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

export const handlePaCommunityOutlets = async (
  params: Readonly<{
    name?: string | undefined;
    type?: "community_club" | "passion_wave" | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getPaCommunityOutlets(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: renderDirectoryResult(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const handlePaResidentNetworkCentres = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getPaResidentNetworkCentres(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: renderDirectoryResult(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const paToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_pa_community_outlets",
    description: "Search People's Association community clubs and PAssion WaVe outlets with optional postal-code or proximity filters.",
    surface: "canonical",
    inputSchema: PaCommunityOutletsInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handlePaCommunityOutlets(PaCommunityOutletsSchema.parse(input)),
  },
  {
    name: "sg_pa_resident_network_centres",
    description: "Search People's Association residents' committee and residents' network centres with optional postal-code or proximity filters.",
    surface: "canonical",
    inputSchema: PaResidentNetworkCentresInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handlePaResidentNetworkCentres(PaResidentNetworkCentresSchema.parse(input)),
  },
];
