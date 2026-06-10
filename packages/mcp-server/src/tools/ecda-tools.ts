import {
  EcdaChildcareCentresInputSchema,
  EcdaChildcareCentresSchema,
  formatResponse,
  resolveOutputFormat,
} from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { toDirectoryGeoFeatures } from "../apis/civic/utils.js";
import { getEcdaChildcareCentres } from "../apis/ecda/client.js";
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

export const handleEcdaChildcareCentres = async (
  params: Readonly<{
    name?: string | undefined;
    postalCode?: string | undefined;
    centreType?: string | undefined;
    operatorType?: string | undefined;
    hasVacancy?: boolean | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getEcdaChildcareCentres(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: renderDirectoryResult(data as unknown as Record<string, unknown>[], format) }],
    structuredContent: { records: data },
  };
};

export const ecdaToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_ecda_childcare_centres",
    description: "Search ECDA childcare centres with optional vacancy, operator, postal-code, or proximity filters.",
    surface: "canonical",
    inputSchema: EcdaChildcareCentresInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handleEcdaChildcareCentres(EcdaChildcareCentresSchema.parse(input)),
  },
];
