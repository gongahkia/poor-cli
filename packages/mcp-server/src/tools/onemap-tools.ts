import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, OneMapGeocodeSchema, OneMapReverseGeocodeSchema, OneMapRouteSchema, OneMapPopulationSchema, OneMapConvertCoordsSchema, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { geocode, reverseGeocode, getRoute, getPopulationData, convertSVY21toWGS84, convertWGS84toSVY21 } from "../apis/onemap/client.js";
import { registerTool } from "./registry.js";

export const handleOneMapGeocode = async (
  params: Readonly<{ searchVal: string; limit?: number | undefined }>,
): Promise<ToolResult> => {
  const results = await geocode(params.searchVal, params.limit);
  const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
  return { content: [{ type: "text", text }] };
};

export const handleOneMapPopulation = async (
  params: Readonly<{ planningArea: string; year?: string | undefined; dataType?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const result = await getPopulationData(
    params.planningArea,
    params.year,
    params.dataType as Parameters<typeof getPopulationData>[2],
  );
  const fmt = resolveOutputFormat(params.format);
  const text = formatResponse(result.data as unknown as Record<string, unknown>[], fmt);
  return { content: [{ type: "text", text: `## ${result.planningArea} (${result.year})\n\n${text}` }] };
};

export const registerOneMapTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_onemap_geocode",
    description: "Convert a Singapore address, building name, or postal code to coordinates. Returns latitude, longitude, full address, and postal code.",
    inputSchema: OneMapGeocodeSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleOneMapGeocode(validateInput(OneMapGeocodeSchema, input));
    },
  });

  registerTool(server, {
    name: "sg_onemap_reverse_geocode",
    description: "Convert coordinates to a Singapore address. Returns the nearest building, block, street, and postal code within the search radius.",
    inputSchema: OneMapReverseGeocodeSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { lat, lng, buffer } = validateInput(OneMapReverseGeocodeSchema, input);
      const result = await reverseGeocode(lat, lng, buffer);
      if (result === null) {
        return { content: [{ type: "text", text: "No results found within the specified radius." }] };
      }
      const text = formatResponse(result as unknown as Record<string, unknown>, "markdown");
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_onemap_route",
    description: "Get routing directions between two Singapore locations. Supports public transport (bus/MRT), driving, walking, and cycling.",
    inputSchema: OneMapRouteSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { startLat, startLng, endLat, endLng, routeType } = validateInput(OneMapRouteSchema, input);
      const result = await getRoute(startLat, startLng, endLat, endLng, routeType);
      const summary = `Distance: ${(result.totalDistance / 1000).toFixed(1)}km | Time: ${Math.ceil(result.totalTime / 60)} min`;
      const instructions = result.instructions.map((s) => `${s.instruction} on ${s.road} (${s.distance}m)`).join("\n");
      return { content: [{ type: "text", text: `${summary}\n\n${instructions}` }] };
    },
  });

  registerTool(server, {
    name: "sg_onemap_population",
    description: "Get demographic data for a Singapore planning area. Includes population totals, age distribution, ethnicity, housing type, education, and income data.",
    inputSchema: OneMapPopulationSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleOneMapPopulation(validateInput(OneMapPopulationSchema, input));
    },
  });

  registerTool(server, {
    name: "sg_onemap_convert_coords",
    description: "Convert between SVY21 (Singapore) and WGS84 (GPS) coordinate systems.",
    inputSchema: OneMapConvertCoordsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { from, x, y } = validateInput(OneMapConvertCoordsSchema, input);
      if (from === "SVY21") {
        const result = await convertSVY21toWGS84(x, y);
        return { content: [{ type: "text", text: `Latitude: ${result.lat}\nLongitude: ${result.lng}` }] };
      } else {
        const result = await convertWGS84toSVY21(x, y);
        return { content: [{ type: "text", text: `Easting (X): ${result.x}\nNorthing (Y): ${result.y}` }] };
      }
    },
  });
};
