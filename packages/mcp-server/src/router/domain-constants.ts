export const PLANNING_AREAS = [
  "ang mo kio", "bedok", "bishan", "bukit batok", "bukit merah", "bukit panjang",
  "bukit timah", "central water catchment", "changi", "changi bay", "choa chu kang",
  "clementi", "downtown core", "geylang", "hougang", "jurong east", "jurong west",
  "kallang", "lim chu kang", "mandai", "marine parade", "museum", "newton", "novena",
  "orchard", "outram", "pasir ris", "paya lebar", "pioneer", "punggol", "queenstown",
  "river valley", "rochor", "seletar", "sembawang", "sengkang", "serangoon",
  "simpang", "singapore river", "southern islands", "sungei kadut", "tampines",
  "tanglin", "tengah", "toa payoh", "tuas", "western islands", "western water catchment",
  "woodlands", "yishun",
] as const;

export const REGIONS = ["north", "south", "east", "west", "central"] as const;
export const ROUTE_MODES = ["walk", "drive", "pt", "cycle"] as const;
export const OUTPUT_FORMATS = ["json", "markdown", "csv", "geojson"] as const;
export const COORDINATE_SYSTEMS = ["SVY21", "WGS84"] as const;

export const toTitleCase = (value: string): string => {
  return value
    .split(" ")
    .filter((part) => part !== "")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};
