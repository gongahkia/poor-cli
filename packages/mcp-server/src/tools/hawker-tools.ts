import { formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { z } from "zod";
import { getHawkerCentres } from "../apis/hawker/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const HawkerCentresSchema = z.object({
  name: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

export const handleHawkerCentres = async (
  params: Readonly<{
    name?: string;
    limit?: number;
    format?: OutputFormat;
  }>,
): Promise<ToolResult> => {
  const data = await getHawkerCentres(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return { content: [{ type: "text", text }], structuredContent: { records: data } };
};

export const hawkerToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_hawker_centres",
    description: "List hawker centres in Singapore with address, coordinates, and stall counts from data.gov.sg.",
    surface: "canonical",
    inputSchema: HawkerCentresSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = HawkerCentresSchema.parse(input);
      return handleHawkerCentres(parsed);
    },
  },
];
