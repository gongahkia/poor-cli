import { z } from "zod";
import { formatResponse, validateInput } from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import {
  buildPulseMobilitySnapshot,
  buildPulseSnapshot,
  buildPulseWeatherSnapshot,
  explainPulseSnapshot,
} from "../pulse/aggregator.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const PulseInputSchema = z.object({
  area: z.string().optional(),
  region: z.string().optional(),
  stationId: z.string().optional(),
  focus: z.enum(["mobility", "weather", "all"]).optional(),
});

const cleanPulseInput = (params: z.infer<typeof PulseInputSchema>) => ({
  ...(params.area === undefined ? {} : { area: params.area }),
  ...(params.region === undefined ? {} : { region: params.region }),
  ...(params.stationId === undefined ? {} : { stationId: params.stationId }),
  ...(params.focus === undefined ? {} : { focus: params.focus }),
});

const result = (payload: Readonly<Record<string, unknown>>): ToolResult => ({
  content: [{ type: "text", text: formatResponse(payload, "json") }],
  structuredContent: payload,
});

const handlePulseSnapshot = async (input: unknown): Promise<ToolResult> => {
  const params = validateInput(PulseInputSchema, input);
  const snapshot = await buildPulseSnapshot(cleanPulseInput(params));
  return result({ snapshot });
};

const handlePulseMobility = async (): Promise<ToolResult> => {
  const payload = await buildPulseMobilitySnapshot();
  return result(payload);
};

const handlePulseWeather = async (input: unknown): Promise<ToolResult> => {
  const params = validateInput(PulseInputSchema, input);
  const payload = await buildPulseWeatherSnapshot(cleanPulseInput(params));
  return result(payload);
};

const handlePulseExplain = async (input: unknown): Promise<ToolResult> => {
  const params = validateInput(PulseInputSchema, input);
  const snapshot = await buildPulseSnapshot(cleanPulseInput(params));
  return result({ snapshot, explanation: explainPulseSnapshot(snapshot), aiUsed: false });
};

export const pulseToolDefinitions = [
  {
    name: "swee_pulse_snapshot",
    description: "Return a source-backed Singapore mobility and weather Pulse snapshot with provenance, freshness, gaps, and recommended actions.",
    surface: "canonical",
    preferred: true,
    inputSchema: PulseInputSchema.shape,
    toolsets: ["public"],
    handler: handlePulseSnapshot,
  },
  {
    name: "swee_pulse_mobility",
    description: "Return deterministic Swee Pulse mobility signals from LTA traffic, road, rail, and camera source adapters.",
    surface: "canonical",
    inputSchema: z.object({}).shape,
    toolsets: ["public"],
    handler: handlePulseMobility,
  },
  {
    name: "swee_pulse_weather",
    description: "Return deterministic Swee Pulse weather signals from NEA forecast, air-quality, and rainfall source adapters.",
    surface: "canonical",
    inputSchema: PulseInputSchema.shape,
    toolsets: ["public"],
    handler: handlePulseWeather,
  },
  {
    name: "swee_pulse_explain",
    description: "Explain the current Swee Pulse snapshot with deterministic fallback text and no AI dependency.",
    surface: "canonical",
    inputSchema: PulseInputSchema.shape,
    toolsets: ["public"],
    handler: handlePulseExplain,
  },
] as const satisfies readonly RegisteredToolDefinition[];
