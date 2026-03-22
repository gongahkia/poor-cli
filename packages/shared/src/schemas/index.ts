import { z } from "zod";
import type { ZodSchema } from "zod";
import { ValidationError } from "../errors.js";

export const SingStatSearchSchema = z.object({
  keyword: z.string().min(1),
  limit: z.number().int().positive().optional(),
});

export const SingStatTableSchema = z.object({
  tableId: z.string().min(1),
  timeFilter: z.string().optional(),
  variables: z.array(z.string()).optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
});

export const SingStatBrowseSchema = z.object({
  category: z.string().optional(),
});

export const SingStatTimeseriesSchema = z.object({
  tableId: z.string().min(1),
  indicator: z.string().min(1),
  startYear: z.number().int(),
  endYear: z.number().int(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
});

export const SingStatCompareSchema = z.object({
  queries: z.array(
    z.object({
      tableId: z.string().min(1),
      indicator: z.string().min(1),
      label: z.string().min(1),
    }),
  ),
  startYear: z.number().int().optional(),
  endYear: z.number().int().optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
});

export const MasExchangeRateSchema = z.object({
  currency: z.string().length(3).optional(),
  date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

export const MasInterestRateSchema = z.object({
  date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

export const MasFinancialStatsSchema = z.object({
  date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

export const OneMapGeocodeSchema = z.object({
  searchVal: z.string().min(1),
  limit: z.number().int().positive().optional(),
});

export const OneMapReverseGeocodeSchema = z.object({
  lat: z.number(),
  lng: z.number(),
  buffer: z.number().positive().optional(),
});

export const OneMapRouteSchema = z.object({
  startLat: z.number(),
  startLng: z.number(),
  endLat: z.number(),
  endLng: z.number(),
  routeType: z.enum(["walk", "drive", "pt", "cycle"]),
  date: z.string().optional(),
  time: z.string().optional(),
});

export const OneMapPopulationSchema = z.object({
  planningArea: z.string().min(1),
  year: z.string().optional(),
  dataType: z
    .enum([
      "getEconomicStatus",
      "getEthnicGroup",
      "getHouseholdMonthlyIncomeWork",
      "getPopulationAgeGroup",
      "getSpokenAtHome",
      "getTenantHouseholdSize",
      "getTypeOfDwellingHousehold",
    ])
    .optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
});

export const OneMapConvertCoordsSchema = z.object({
  from: z.enum(["SVY21", "WGS84"]),
  x: z.number(),
  y: z.number(),
});

export const UraPropertyTransactionsSchema = z.object({
  propertyType: z.enum(["residential", "commercial", "industrial"]).optional(),
  area: z.string().optional(),
  period: z.string().optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
});

export const UraPlanningAreaSchema = z.object({
  lat: z.number().optional(),
  lng: z.number().optional(),
  planningArea: z.string().optional(),
});

export const UraDevChargesSchema = z.object({
  useGroup: z.string().optional(),
  sector: z.string().optional(),
});

export const DatagovSearchSchema = z.object({
  keyword: z.string().min(1),
  limit: z.number().int().positive().optional(),
});

export const DatagovGetSchema = z.object({
  datasetId: z.string().min(1),
  resourceIndex: z.number().int().nonnegative().optional(),
  limit: z.number().int().positive().optional(),
  offset: z.number().int().nonnegative().optional(),
  filters: z.record(z.string()).optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
});

export const DatagovBrowseSchema = z.object({
  collection: z.string().optional(),
});

export const HealthCheckSchema = z.object({}).optional();

export const KeySetSchema = z.object({
  apiName: z.string().min(1),
  key: z.string().min(1),
});

export const KeyListSchema = z.object({}).optional();

export const KeyDeleteSchema = z.object({
  apiName: z.string().min(1),
});

export const CacheStatsSchema = z.object({}).optional();

export const CacheClearSchema = z.object({
  api: z.string().optional(),
});

export const ConfigGetSchema = z.object({}).optional();

export const ConfigSetSchema = z.object({
  key: z.string().min(1),
  value: z.string().min(1),
});

export const QuerySchema = z.object({
  query: z.string().min(1),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
});

export const validateInput = <T>(schema: ZodSchema<T>, input: unknown): T => {
  const result = schema.safeParse(input);
  if (!result.success) {
    throw new ValidationError(
      `Invalid input: ${result.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join(", ")}`,
      result.error.issues,
    );
  }
  return result.data;
};
