import { describe, expect, it } from "vitest";
import {
  AcraEntitiesSchema,
  BoaArchitectsSchema,
  BoaArchitectureFirmsSchema,
  BcaLicensedBuildersSchema,
  BcaRegisteredContractorsSchema,
  BriefArtifactSchema,
  BusinessDossierSchema,
  CeaSalespersonsSchema,
  DatagovResourcesSchema,
  DatagovRowsSchema,
  EnvironmentBriefSchema,
  HdbRentalPricesSchema,
  HdbResalePricesSchema,
  HlbHotelsSchema,
  HsaHealthProductLicenseesSchema,
  HsaLicensedPharmaciesSchema,
  MacroBriefSchema,
  OneMapRouteSchema,
  QueryBlockedResultSchema,
  QueryCompletedResultSchema,
  QueryFailedResultSchema,
  QueryOutcomeSchema,
  QueryUnsupportedResultSchema,
  PropertyBriefSchema,
  QuerySchema,
  TransportBriefSchema,
} from "../schemas/index.js";

describe("query and HDB schema contracts", () => {
  it("accepts sg_query plan mode", () => {
    expect(
      QuerySchema.safeParse({
        query: "Macro snapshot of Singapore",
        mode: "plan",
      }).success,
    ).toBe(true);
  });

  it("rejects unsupported sg_query fields", () => {
    expect(
      QuerySchema.safeParse({
        query: "Macro snapshot of Singapore",
        depth: "high",
      }).success,
    ).toBe(false);
  });

  it("accepts bounded HDB resale filters", () => {
    expect(
      HdbResalePricesSchema.safeParse({
        town: "Bedok",
        flatType: "4 ROOM",
        startMonth: "2026-01",
        endMonth: "2026-03",
        limit: 20,
      }).success,
    ).toBe(true);
  });

  it("rejects malformed HDB month filters", () => {
    expect(
      HdbRentalPricesSchema.safeParse({
        startMonth: "2026/01",
      }).success,
    ).toBe(false);
  });

  it("rejects unsupported OneMap route fields", () => {
    expect(
      OneMapRouteSchema.safeParse({
        startLat: 1.3,
        startLng: 103.8,
        endLat: 1.31,
        endLng: 103.81,
        routeType: "drive",
        date: "2026-03-24",
      }).success,
    ).toBe(false);
  });

  it("requires at least one exact-match filter for CEA lookups", () => {
    expect(
      CeaSalespersonsSchema.safeParse({
        limit: 10,
      }).success,
    ).toBe(false);
  });

  it("accepts bounded BCA direct-tool filters", () => {
    expect(
      BcaLicensedBuildersSchema.safeParse({
        companyName: "ABC CONSTRUCTION PTE LTD",
        limit: 10,
      }).success,
    ).toBe(true);
    expect(
      BcaRegisteredContractorsSchema.safeParse({
        workhead: "CW01",
        grade: "C3",
      }).success,
    ).toBe(true);
  });

  it("accepts bounded BOA, HSA, and HLB direct-tool filters", () => {
    expect(
      BoaArchitectsSchema.safeParse({
        name: "ALICE TAN",
      }).success,
    ).toBe(true);
    expect(
      BoaArchitectureFirmsSchema.safeParse({
        firmName: "DESIGN LAB PTE LTD",
      }).success,
    ).toBe(true);
    expect(
      HsaLicensedPharmaciesSchema.safeParse({
        postalCode: "238841",
      }).success,
    ).toBe(true);
    expect(
      HsaHealthProductLicenseesSchema.safeParse({
        companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
      }).success,
    ).toBe(true);
    expect(
      HlbHotelsSchema.safeParse({
        keeperName: "RAFFLES HOTEL SINGAPORE",
        format: "geojson",
      }).success,
    ).toBe(true);
  });

  it("requires an entity name or UEN for ACRA lookups", () => {
    expect(
      AcraEntitiesSchema.safeParse({
        limit: 5,
      }).success,
    ).toBe(false);
    expect(
      AcraEntitiesSchema.safeParse({
        entityName: "ABC CONSTRUCTION PTE LTD",
      }).success,
    ).toBe(true);
  });

  it("accepts dataset resource inspection and bounded row reads", () => {
    expect(
      DatagovResourcesSchema.safeParse({
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        format: "json",
      }).success,
    ).toBe(true);
    expect(
      DatagovRowsSchema.safeParse({
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        filters: {
          town: "BEDOK",
          floor_area_sqm: 92,
          active: true,
        },
        limit: 20,
        offset: 0,
        sort: "month desc",
      }).success,
    ).toBe(true);
  });

  it("requires a datasetId or resourceId for data.gov row reads", () => {
    expect(
      DatagovRowsSchema.safeParse({
        limit: 10,
      }).success,
    ).toBe(false);
  });

  it("accepts bounded additive brief schemas", () => {
    expect(
      BusinessDossierSchema.safeParse({
        entityName: "ABC CONSTRUCTION PTE LTD",
        workhead: "CW01",
        modules: ["acra", "bca", "gebiz"],
        sectorHints: ["construction", "procurement"],
        format: "markdown",
      }).success,
    ).toBe(true);
    expect(
      PropertyBriefSchema.safeParse({
        postalCode: "168742",
        includeEnvironment: true,
        format: "json",
      }).success,
    ).toBe(true);
    expect(
      MacroBriefSchema.safeParse({
        currency: "USD",
        startDate: "2025-01-01",
        endDate: "2025-01-31",
      }).success,
    ).toBe(true);
    expect(
      TransportBriefSchema.safeParse({
        busStopCode: "83139",
        serviceNo: "851",
        format: "json",
      }).success,
    ).toBe(true);
    expect(
      EnvironmentBriefSchema.safeParse({
        area: "Tampines",
        region: "East",
        stationId: "S107",
        format: "markdown",
      }).success,
    ).toBe(true);
  });

  it("rejects empty additive briefs", () => {
    expect(
      BusinessDossierSchema.safeParse({
        format: "json",
      }).success,
    ).toBe(false);
    expect(
      PropertyBriefSchema.safeParse({
        includeTransport: true,
      }).success,
    ).toBe(false);
    expect(
      TransportBriefSchema.safeParse({
        serviceNo: "851",
      }).success,
    ).toBe(false);
  });

  it("accepts the expanded brief artifact envelope", () => {
    expect(
      BriefArtifactSchema.safeParse({
        title: "Macro Brief",
        summary: [{ label: "USD/SGD", value: 1.35, source: "MAS" }],
        evidence: [{ label: "FX rows", value: 1, source: "MAS" }],
        records: { exchangeRates: [] },
        gaps: [{ code: "NONE", message: "No gaps." }],
        provenance: [{
          source: "MAS",
          tool: "sg_mas_exchange_rates",
          coverage: "Exchange-rate coverage.",
          authRequired: false,
          recordCount: 1,
        }],
        freshness: [{
          source: "MAS",
          observedAt: "2026-03-26T00:00:00.000Z",
          upstreamTimestamp: "2026-03-26",
        }],
        limits: [{ code: "SNAPSHOT_ONLY", message: "Starter brief only." }],
      }).success,
    ).toBe(true);
  });

  it("accepts a blocked sg_query result with structured blockers", () => {
    expect(
      QueryBlockedResultSchema.safeParse({
        status: "blocked",
        mode: "execute",
        workflow: "route_plan",
        intent: "geospatial",
        apis: ["onemap"],
        confidence: 0.88,
        toolsUsed: ["sg_onemap_geocode", "sg_onemap_route"],
        steps: [
          {
            id: "route_origin_geocode",
            purpose: "Resolve the origin postal code to coordinates.",
            tool: "sg_onemap_geocode",
            input: { searchVal: "049178" },
          },
        ],
        blockers: [
          {
            field: "destinationPostalCode",
            reason: "Provide a Singapore postal code or coordinates for the destination.",
            directTool: "sg_onemap_geocode",
            exampleInput: { searchVal: "048616" },
            suggestedPrompt: "Walk from 049178 to 048616",
          },
        ],
        reason: "sg_query needs a destination before it can continue the route workflow.",
        suggestion: "Provide the missing destination postal code or coordinates and retry.",
        routingExplanation: "Routed to route_plan (confidence 0.88) via sg_onemap_geocode → sg_onemap_route. Drop to direct sg_* tools when you have exact identifiers.",
      }).success,
    ).toBe(true);
  });

  it("accepts completed, unsupported, and failed sg_query outcomes via the shared union schema", () => {
    expect(
      QueryOutcomeSchema.safeParse({
        status: "completed",
        mode: "execute",
        workflow: "macro_brief",
        intent: "macro",
        apis: ["mas", "singstat"],
        confidence: 0.92,
        toolsUsed: ["sg_macro_brief"],
        steps: [
          {
            id: "macro_brief",
            purpose: "Build a compact Singapore macro starter brief.",
            tool: "sg_macro_brief",
            status: "completed",
            input: { currency: "USD" },
            structuredOutput: { record: { title: "Macro Brief" } },
          },
        ],
        routingExplanation: "Routed to macro_brief (confidence 0.92) via sg_macro_brief. Drop to direct sg_* tools when you have exact identifiers.",
        continuationHints: ["Call sg_singstat_table with tableId \"M015631\" for detailed data."],
      }).success,
    ).toBe(true);

    expect(
      QueryUnsupportedResultSchema.safeParse({
        status: "unsupported",
        mode: "execute",
        reason: "sg_query does not run comparison workflows automatically.",
        suggestion: "Call the relevant direct tool separately for each item you want to compare.",
      }).success,
    ).toBe(true);

    expect(
      QueryFailedResultSchema.safeParse({
        status: "failed",
        mode: "execute",
        workflow: "dataset_discovery",
        intent: "dataset",
        apis: ["datagov"],
        confidence: 0.82,
        toolsUsed: ["sg_datagov_search", "sg_datagov_get"],
        steps: [
          {
            id: "dataset_search",
            purpose: "Search data.gov.sg for relevant datasets.",
            tool: "sg_datagov_search",
            status: "failed",
            input: { keyword: "hawker centres" },
            error: {
              source: "sg_datagov_search",
              tool: "sg_datagov_search",
              code: "UPSTREAM_ERROR",
              retryable: true,
              message: "Upstream service unavailable",
            },
          },
        ],
        routingExplanation: "Routed to dataset_discovery (confidence 0.82) via sg_datagov_search → sg_datagov_get. Drop to direct sg_* tools when you have exact identifiers.",
        failedStep: {
          id: "dataset_search",
          purpose: "Search data.gov.sg for relevant datasets.",
          tool: "sg_datagov_search",
          status: "failed",
          input: { keyword: "hawker centres" },
          error: {
            source: "sg_datagov_search",
            tool: "sg_datagov_search",
            code: "UPSTREAM_ERROR",
            retryable: true,
            message: "Upstream service unavailable",
          },
        },
      }).success,
    ).toBe(true);

    expect(
      QueryCompletedResultSchema.safeParse({
        status: "completed",
        mode: "execute",
        workflow: "transport_brief",
        intent: "transport",
        apis: ["lta"],
        confidence: 0.9,
        toolsUsed: ["sg_transport_brief"],
        steps: [
          {
            id: "transport_brief",
            purpose: "Build a live transport operations brief.",
            tool: "sg_transport_brief",
            status: "completed",
            input: {},
          },
        ],
        routingExplanation: "Routed to transport_brief (confidence 0.90) via sg_transport_brief. Drop to direct sg_* tools when you have exact identifiers.",
      }).success,
    ).toBe(true);
  });
});
