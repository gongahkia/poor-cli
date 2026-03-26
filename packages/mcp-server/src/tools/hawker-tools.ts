import { formatResponse, HawkerCentresSchema, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getHawkerCentres } from "../apis/hawker/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleHawkerCentres = async (
  params: Readonly<{
    name?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
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
