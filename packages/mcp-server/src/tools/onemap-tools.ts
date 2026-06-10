import { validateInput, OneMapGeocodeSchema, OneMapReverseGeocodeSchema, OneMapRouteSchema, OneMapPopulationSchema, OneMapConvertCoordsSchema, formatResponse, resolveOutputFormat } from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { geocode, reverseGeocode, getRoute, getPopulationData, convertSVY21toWGS84, convertWGS84toSVY21 } from "../apis/onemap/client.js";
import { buildMapPayloadFromPoints, buildMapPayloadFromRoute, withMapUiMetadata } from "./map-payload.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const MAP_TOOL_META = withMapUiMetadata(undefined);

export const handleOneMapGeocode = async (
  params: Readonly<{ searchVal: string; limit?: number | undefined }>,
): Promise<ToolResult> => {
  const results = await geocode(params.searchVal, params.limit);
  const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
  const mapPayload = buildMapPayloadFromPoints("sg_onemap_geocode", results.map((result) => ({
    lat: result.lat,
    lng: result.lng,
    label: result.building || result.address || result.postal || params.searchVal,
    description: result.address,
  })));
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: results,
      ...(mapPayload === null ? {} : { mapPayload }),
    },
    ...(mapPayload === null ? {} : { _meta: MAP_TOOL_META }),
  };
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
  return {
    content: [{ type: "text", text: `## ${result.planningArea} (${result.year})\n\n${text}` }],
    structuredContent: {
      planningArea: result.planningArea,
      year: result.year,
      records: result.data,
    },
  };
};

export const handleOneMapRoute = async (
  params: Readonly<{
    startLat: number;
    startLng: number;
    endLat: number;
    endLng: number;
    routeType: "walk" | "drive" | "pt" | "cycle";
  }>,
): Promise<ToolResult> => {
  const result = await getRoute(
    params.startLat,
    params.startLng,
    params.endLat,
    params.endLng,
    params.routeType,
  );
  const summary = `Distance: ${(result.totalDistance / 1000).toFixed(1)}km | Time: ${Math.ceil(result.totalTime / 60)} min`;
  const instructions = result.instructions.map((s) => `${s.instruction} on ${s.road} (${s.distance}m)`).join("\n");
  const mapPayload = buildMapPayloadFromRoute({
    sourceTool: "sg_onemap_route",
    start: {
      lat: params.startLat,
      lng: params.startLng,
      label: "Start",
    },
    end: {
      lat: params.endLat,
      lng: params.endLng,
      label: "End",
    },
  });
  return {
    content: [{ type: "text", text: `${summary}\n\n${instructions}` }],
    structuredContent: {
      record: result,
      mapPayload,
      requestedRoute: {
        startLat: params.startLat,
        startLng: params.startLng,
        endLat: params.endLat,
        endLng: params.endLng,
        routeType: params.routeType,
      },
    },
    _meta: MAP_TOOL_META,
  };
};

export const handleOneMapReverseGeocode = async (
  params: Readonly<{ lat: number; lng: number; buffer?: number | undefined }>,
): Promise<ToolResult> => {
  const result = await reverseGeocode(params.lat, params.lng, params.buffer);
  if (result === null) {
    return {
      content: [{ type: "text", text: "No results found within the specified radius." }],
      structuredContent: {
        record: null,
        requestedScope: {
          lat: params.lat,
          lng: params.lng,
          ...(params.buffer === undefined ? {} : { buffer: params.buffer }),
        },
      },
    };
  }
  const text = formatResponse(result as unknown as Record<string, unknown>, "markdown");
  const mapPayload = buildMapPayloadFromPoints("sg_onemap_reverse_geocode", [{
    lat: result.lat,
    lng: result.lng,
    label: result.building || result.address || result.postal || "Resolved address",
    description: result.address,
  }]);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      record: result,
      ...(mapPayload === null ? {} : { mapPayload }),
    },
    ...(mapPayload === null ? {} : { _meta: MAP_TOOL_META }),
  };
};

export const handleOneMapConvertCoords = async (
  params: Readonly<{ from: "SVY21" | "WGS84"; x: number; y: number }>,
): Promise<ToolResult> => {
  if (params.from === "SVY21") {
    const result = await convertSVY21toWGS84(params.x, params.y);
    return {
      content: [{ type: "text", text: `Latitude: ${result.lat}\nLongitude: ${result.lng}` }],
      structuredContent: {
        record: result,
      },
    };
  }

  const result = await convertWGS84toSVY21(params.x, params.y);
  return {
    content: [{ type: "text", text: `Easting (X): ${result.x}\nNorthing (Y): ${result.y}` }],
    structuredContent: {
      record: result,
    },
  };
};

export const onemapToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_onemap_geocode",
    description: "Convert a Singapore address, building name, or postal code to coordinates. Returns latitude, longitude, full address, and postal code.",
    surface: "canonical",
    _meta: MAP_TOOL_META,
    inputSchema: OneMapGeocodeSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleOneMapGeocode(validateInput(OneMapGeocodeSchema, input));
    },
  },

  {
    name: "sg_onemap_reverse_geocode",
    description: "Convert coordinates to a Singapore address. Returns the nearest building, block, street, and postal code within the search radius.",
    surface: "canonical",
    _meta: MAP_TOOL_META,
    inputSchema: OneMapReverseGeocodeSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleOneMapReverseGeocode(validateInput(OneMapReverseGeocodeSchema, input));
    },
  },

  {
    name: "sg_onemap_route",
    description: "Get routing directions between two Singapore locations. Supports public transport (bus/MRT), driving, walking, and cycling.",
    surface: "canonical",
    _meta: MAP_TOOL_META,
    inputSchema: OneMapRouteSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleOneMapRoute(validateInput(OneMapRouteSchema, input));
    },
  },

  {
    name: "sg_onemap_population",
    description: "Get demographic data for a Singapore planning area. Includes population totals, age distribution, ethnicity, housing type, education, and income data.",
    surface: "canonical",
    inputSchema: OneMapPopulationSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleOneMapPopulation(validateInput(OneMapPopulationSchema, input));
    },
  },

  {
    name: "sg_onemap_convert_coords",
    description: "Convert between SVY21 (Singapore) and WGS84 (GPS) coordinate systems.",
    surface: "canonical",
    inputSchema: OneMapConvertCoordsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleOneMapConvertCoords(validateInput(OneMapConvertCoordsSchema, input));
    },
  },
];
