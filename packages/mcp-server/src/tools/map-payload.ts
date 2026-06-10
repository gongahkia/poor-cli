export const MAP_UI_RESOURCE_URI = "ui://sg/map-preview";

export type MapMarker = {
  readonly lat: number;
  readonly lng: number;
  readonly label: string;
  readonly description?: string;
};

export type MapPolyline = {
  readonly label: string;
  readonly approximate?: boolean;
  readonly coordinates: readonly {
    readonly lat: number;
    readonly lng: number;
  }[];
};

export type MapBounds = {
  readonly north: number;
  readonly south: number;
  readonly east: number;
  readonly west: number;
};

export type MapPayload = {
  readonly markers: readonly MapMarker[];
  readonly polylines: readonly MapPolyline[];
  readonly bounds: MapBounds | null;
  readonly layers: readonly {
    readonly id: string;
    readonly label: string;
    readonly kind: "markers" | "route";
  }[];
  readonly legend: readonly {
    readonly label: string;
    readonly kind: "marker" | "line";
    readonly approximate?: boolean;
  }[];
  readonly sourceTool: string;
};

const toFiniteNumber = (value: unknown): number | null => {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

const toBounds = (
  markers: readonly MapMarker[],
  polylines: readonly MapPolyline[],
): MapBounds | null => {
  const coordinates = [
    ...markers.map((marker) => ({ lat: marker.lat, lng: marker.lng })),
    ...polylines.flatMap((polyline) => polyline.coordinates),
  ];

  if (coordinates.length === 0) {
    return null;
  }

  return coordinates.reduce<MapBounds>((bounds, point) => ({
    north: Math.max(bounds.north, point.lat),
    south: Math.min(bounds.south, point.lat),
    east: Math.max(bounds.east, point.lng),
    west: Math.min(bounds.west, point.lng),
  }), {
    north: coordinates[0]!.lat,
    south: coordinates[0]!.lat,
    east: coordinates[0]!.lng,
    west: coordinates[0]!.lng,
  });
};

export const withMapUiMetadata = <T extends Readonly<Record<string, unknown>> | undefined>(
  meta: T,
) => {
  const nextMeta = {
    ...(meta ?? {}),
    ui: {
      resourceUri: MAP_UI_RESOURCE_URI,
    },
    "ui/resourceUri": MAP_UI_RESOURCE_URI,
  };
  return nextMeta;
};

export const buildMapPayloadFromPoints = (
  sourceTool: string,
  points: readonly {
    readonly lat: number;
    readonly lng: number;
    readonly label: string;
    readonly description?: string;
  }[],
): MapPayload | null => {
  if (points.length === 0) {
    return null;
  }

  const markers = points.map((point) => ({
    lat: point.lat,
    lng: point.lng,
    label: point.label,
    ...(point.description === undefined ? {} : { description: point.description }),
  }));

  return {
    markers,
    polylines: [],
    bounds: toBounds(markers, []),
    layers: [{ id: "markers", label: "Locations", kind: "markers" }],
    legend: [{ label: "Location", kind: "marker" }],
    sourceTool,
  };
};

export const buildMapPayloadFromRoute = (options: {
  readonly sourceTool: string;
  readonly start: { readonly lat: number; readonly lng: number; readonly label: string };
  readonly end: { readonly lat: number; readonly lng: number; readonly label: string };
}): MapPayload => {
  const markers: readonly MapMarker[] = [
    { lat: options.start.lat, lng: options.start.lng, label: options.start.label },
    { lat: options.end.lat, lng: options.end.lng, label: options.end.label },
  ];
  const polylines: readonly MapPolyline[] = [{
    label: "Approximate route",
    approximate: true,
    coordinates: [
      { lat: options.start.lat, lng: options.start.lng },
      { lat: options.end.lat, lng: options.end.lng },
    ],
  }];

  return {
    markers,
    polylines,
    bounds: toBounds(markers, polylines),
    layers: [
      { id: "markers", label: "Endpoints", kind: "markers" },
      { id: "route", label: "Approximate route", kind: "route" },
    ],
    legend: [
      { label: "Endpoint", kind: "marker" },
      { label: "Approximate route", kind: "line", approximate: true },
    ],
    sourceTool: options.sourceTool,
  };
};

const buildLabel = (row: Readonly<Record<string, unknown>>): string => {
  for (const key of ["building", "name", "address", "postal"]) {
    const value = row[key];
    if (typeof value === "string" && value.trim() !== "") {
      return value;
    }
  }
  return "Location";
};

export const buildMapPayloadFromStructuredContent = (
  sourceTool: string,
  structuredContent: Readonly<Record<string, unknown>> | undefined,
): MapPayload | null => {
  if (structuredContent === undefined) {
    return null;
  }

  const existing = structuredContent["mapPayload"];
  if (existing !== undefined && typeof existing === "object" && existing !== null) {
    return existing as MapPayload;
  }

  const record = structuredContent["record"];
  if (record !== undefined && typeof record === "object" && record !== null && !Array.isArray(record)) {
    const lat = toFiniteNumber((record as Record<string, unknown>)["lat"]);
    const lng = toFiniteNumber((record as Record<string, unknown>)["lng"]);
    if (lat !== null && lng !== null) {
      return buildMapPayloadFromPoints(sourceTool, [{
        lat,
        lng,
        label: buildLabel(record as Record<string, unknown>),
      }]);
    }
  }

  const records = structuredContent["records"];
  if (Array.isArray(records)) {
    const points = records.flatMap((row) => {
      if (typeof row !== "object" || row === null || Array.isArray(row)) {
        return [];
      }

      const lat = toFiniteNumber((row as Record<string, unknown>)["lat"]);
      const lng = toFiniteNumber((row as Record<string, unknown>)["lng"]);
      if (lat === null || lng === null) {
        return [];
      }

      return [{
        lat,
        lng,
        label: buildLabel(row as Record<string, unknown>),
      }];
    });
    return points.length === 0 ? null : buildMapPayloadFromPoints(sourceTool, points);
  }

  return null;
};
