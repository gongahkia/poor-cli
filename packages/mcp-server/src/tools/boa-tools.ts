import {
  BoaArchitectsBaseSchema,
  BoaArchitectsSchema,
  BoaArchitectureFirmsBaseSchema,
  BoaArchitectureFirmsSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getBoaArchitects, getBoaArchitectureFirms } from "../apis/boa/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleBoaArchitects = async (
  params: Readonly<{
    name?: string | undefined;
    registrationNo?: string | undefined;
    firmName?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getBoaArchitects(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: { records: data },
  };
};

export const handleBoaArchitectureFirms = async (
  params: Readonly<{
    firmName?: string | undefined;
    email?: string | undefined;
    phone?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getBoaArchitectureFirms(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: { records: data },
  };
};

export const boaToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_boa_architects",
    description: "Look up Board of Architects registered architects by exact architect name, registration number, or architecture firm name.",
    surface: "canonical",
    inputSchema: BoaArchitectsBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleBoaArchitects(validateInput(BoaArchitectsSchema, input)),
  },
  {
    name: "sg_boa_architecture_firms",
    description: "Look up Board of Architects registered architecture firms by exact firm name, email, or phone number.",
    surface: "canonical",
    inputSchema: BoaArchitectureFirmsBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleBoaArchitectureFirms(validateInput(BoaArchitectureFirmsSchema, input)),
  },
];
