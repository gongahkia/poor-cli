import {
  CeaSalespersonsBaseSchema,
  CeaSalespersonsSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { getCeaSalespersons } from "../apis/cea/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleCeaSalespersons = async (
  params: Readonly<{
    salespersonName?: string | undefined;
    registrationNo?: string | undefined;
    estateAgentName?: string | undefined;
    estateAgentLicenseNo?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getCeaSalespersons(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const ceaToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_cea_salespersons",
    description: "Look up CEA salesperson registrations by exact salesperson, registration number, estate agent, or estate-agent licence number.",
    surface: "canonical",
    inputSchema: CeaSalespersonsBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleCeaSalespersons(validateInput(CeaSalespersonsSchema, input)),
  },
];
