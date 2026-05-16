import { formatResponse, EmaElectricityGenerationSchema, resolveOutputFormat } from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { getEmaElectricityGeneration } from "../apis/ema/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleEmaElectricityGeneration = async (
  params: Readonly<{ energyType?: string | undefined; year?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getEmaElectricityGeneration(params);
  const format = resolveOutputFormat(params.format);
  return { content: [{ type: "text", text: formatResponse(data as unknown as Record<string, unknown>[], format) }], structuredContent: { records: data } };
};

export const emaToolDefinitions: readonly RegisteredToolDefinition[] = [{
  name: "sg_ema_electricity_generation",
  description: "Get EMA monthly electricity generation records by energy product type and year via data.gov.sg.",
  surface: "canonical",
  inputSchema: EmaElectricityGenerationSchema.shape,
  handler: async (input: unknown): Promise<ToolResult> => handleEmaElectricityGeneration(EmaElectricityGenerationSchema.parse(input)),
}];
