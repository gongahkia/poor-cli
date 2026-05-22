import { formatResponse } from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import { z } from "zod";
import {
  buildPulseMobility,
  buildPulseSnapshot,
  buildPulseWeather,
  explainPulseSnapshot,
} from "../pulse/aggregator.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const PulseInputSchema = z.object({
  focus: z.string().optional(),
  area: z.string().optional(),
  region: z.string().optional(),
  stationId: z.string().optional(),
});

const result = (record: Readonly<Record<string, unknown>>, markdown?: string): ToolResult => ({
  content: [{ type: "text", text: markdown ?? formatResponse(record, "json") }],
  structuredContent: { record },
});

export const pulseToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "swee_pulse_snapshot",
    description: "Build a Singapore mobility and weather live-ops snapshot with provenance, freshness, and gaps.",
    surface: "canonical",
    toolsets: ["public"],
    inputSchema: PulseInputSchema.shape,
    handler: async (input) => result(await buildPulseSnapshot(PulseInputSchema.parse(input ?? {})) as unknown as Readonly<Record<string, unknown>>),
  },
  {
    name: "swee_pulse_mobility",
    description: "Build Singapore mobility signals from LTA and traffic-image sources.",
    surface: "canonical",
    toolsets: ["public"],
    inputSchema: {},
    handler: async () => result(await buildPulseMobility() as unknown as Readonly<Record<string, unknown>>),
  },
  {
    name: "swee_pulse_weather",
    description: "Build Singapore weather signals from NEA forecast, air-quality, and rainfall sources.",
    surface: "canonical",
    toolsets: ["public"],
    inputSchema: PulseInputSchema.shape,
    handler: async (input) => result(await buildPulseWeather(PulseInputSchema.parse(input ?? {})) as unknown as Readonly<Record<string, unknown>>),
  },
  {
    name: "swee_pulse_explain",
    description: "Generate a deterministic, source-backed explanation for a Swee Pulse snapshot.",
    surface: "canonical",
    toolsets: ["public"],
    inputSchema: PulseInputSchema.shape,
    handler: async (input) => {
      const snapshot = await buildPulseSnapshot(PulseInputSchema.parse(input ?? {}));
      return result({ snapshot, explanation: explainPulseSnapshot(snapshot) }, explainPulseSnapshot(snapshot));
    },
  },
];
