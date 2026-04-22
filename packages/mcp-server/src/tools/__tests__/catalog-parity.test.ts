import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  API_CATALOG,
  BENCHMARK_CATALOG,
  OPS_TAXONOMY_CATALOG,
  PLAYBOOK_CATALOG,
  RECIPE_CATALOG,
  RESOURCE_URIS,
  RUNTIME_CATALOG,
  TOOL_CATALOG,
  WORKFLOW_CATALOG,
} from "../catalog.js";
import {
  NORMALIZED_PLAYBOOK_CATALOG,
  NORMALIZED_RECIPE_CATALOG,
  NORMALIZED_WORKFLOW_CATALOG,
  buildApiCatalog,
  buildToolCatalog,
} from "../catalog-surface.js";
import { registerAllTools } from "../registry.js";
import { ALL_TOOL_DEFINITIONS } from "../tool-set.js";

type ResourceHandler = () => Promise<{
  contents: readonly {
    readonly uri: string;
    readonly text?: string;
    readonly mimeType?: string;
  }[];
}>;

const collectSurface = () => {
  const registeredTools: string[] = [];
  const resourceHandlers = new Map<string, ResourceHandler>();

  const server = {
    registerTool: (name: string) => {
      registeredTools.push(name);
    },
    registerResource: (
      _name: string,
      uriOrTemplate: string | { readonly uriTemplate?: unknown },
      _config: unknown,
      handler: ResourceHandler,
    ) => {
      if (typeof uriOrTemplate === "string") {
        resourceHandlers.set(uriOrTemplate, handler);
      }
    },
    registerPrompt: () => undefined,
  };

  registerAllTools(server as unknown as Parameters<typeof registerAllTools>[0]);

  return { registeredTools, resourceHandlers };
};

const LIVE_TOOL_CATALOG = buildToolCatalog(ALL_TOOL_DEFINITIONS);
const LIVE_API_CATALOG = buildApiCatalog(ALL_TOOL_DEFINITIONS);
const toSerializable = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

describe("tool catalog parity", () => {
  it("contains exactly one entry for each registered public tool", () => {
    const { registeredTools } = collectSurface();
    const catalogNames = LIVE_TOOL_CATALOG.map((tool) => tool.name);

    expect(new Set(catalogNames).size).toBe(catalogNames.length);
    expect(catalogNames.slice().sort()).toEqual(registeredTools.slice().sort());
  });

  it("marks sg_query as the preferred canonical interface in the catalog", () => {
    expect(TOOL_CATALOG.find((tool) => tool.name === "sg_query")).toMatchObject({
      name: "sg_query",
      surface: "canonical",
      preferred: true,
    });
  });

  it("keeps API catalog tool groups in sync with tool catalog entries", () => {
    const catalogNames = new Set(TOOL_CATALOG.map((tool) => tool.name));

    for (const api of API_CATALOG) {
      for (const toolName of api.tools) {
        expect(catalogNames.has(toolName)).toBe(true);
      }
    }
  });

  it("tracks the expected post-tranche public surface counts", () => {
    expect(API_CATALOG).toHaveLength(31);
    expect(TOOL_CATALOG).toHaveLength(90);
  });

  it("keeps the business-diligence tool families visible in catalog resources", () => {
    expect(API_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          name: "CEA",
          tools: ["sg_cea_salespersons"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "BCA",
          tools: ["sg_bca_licensed_builders", "sg_bca_registered_contractors"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "ACRA",
          tools: ["sg_acra_entities"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "BOA",
          tools: ["sg_boa_architects", "sg_boa_architecture_firms"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "HSA",
          tools: ["sg_hsa_licensed_pharmacies", "sg_hsa_health_product_licensees"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "HLB",
          tools: ["sg_hlb_hotels"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "PA",
          tools: ["sg_pa_community_outlets", "sg_pa_resident_network_centres"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "Sport Singapore",
          tools: ["sg_sportsg_facilities"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "ECDA",
          tools: ["sg_ecda_childcare_centres"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "MSF Family Services",
          tools: ["sg_msf_family_services"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "MSF Student Care Services",
          tools: ["sg_msf_student_care_services"],
          preferredInterface: "sg_query",
        }),
        expect.objectContaining({
          name: "MSF Social Service Offices",
          tools: ["sg_msf_social_service_offices"],
          preferredInterface: "sg_query",
        }),
      ]),
    );
    expect(TOOL_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: "sg_acra_entities", surface: "canonical" }),
        expect.objectContaining({ name: "sg_cea_salespersons", surface: "canonical" }),
        expect.objectContaining({ name: "sg_bca_licensed_builders", surface: "canonical" }),
        expect.objectContaining({ name: "sg_bca_registered_contractors", surface: "canonical" }),
        expect.objectContaining({ name: "sg_boa_architects", surface: "canonical" }),
        expect.objectContaining({ name: "sg_boa_architecture_firms", surface: "canonical" }),
        expect.objectContaining({ name: "sg_hsa_licensed_pharmacies", surface: "canonical" }),
        expect.objectContaining({ name: "sg_hsa_health_product_licensees", surface: "canonical" }),
        expect.objectContaining({ name: "sg_hlb_hotels", surface: "canonical" }),
        expect.objectContaining({ name: "sg_pa_community_outlets", surface: "canonical" }),
        expect.objectContaining({ name: "sg_pa_resident_network_centres", surface: "canonical" }),
        expect.objectContaining({ name: "sg_sportsg_facilities", surface: "canonical" }),
        expect.objectContaining({ name: "sg_ecda_childcare_centres", surface: "canonical" }),
        expect.objectContaining({ name: "sg_msf_family_services", surface: "canonical" }),
        expect.objectContaining({ name: "sg_msf_student_care_services", surface: "canonical" }),
        expect.objectContaining({ name: "sg_msf_social_service_offices", surface: "canonical" }),
        expect.objectContaining({ name: "sg_business_dossier", surface: "canonical" }),
        expect.objectContaining({ name: "sg_property_brief", surface: "canonical" }),
        expect.objectContaining({ name: "sg_macro_brief", surface: "canonical" }),
        expect.objectContaining({ name: "sg_transport_brief", surface: "canonical" }),
        expect.objectContaining({ name: "sg_environment_brief", surface: "canonical" }),
        expect.objectContaining({ name: "sg_datagov_resources", surface: "canonical" }),
        expect.objectContaining({ name: "sg_datagov_rows", surface: "canonical" }),
      ]),
    );
  });
});

describe("resource catalog parity", () => {
  it("keeps prompt metadata coverage in sync with every shipped recipe and playbook", () => {
    expect(NORMALIZED_RECIPE_CATALOG.every((entry) => entry.promptMetadata !== undefined)).toBe(true);
    expect(NORMALIZED_PLAYBOOK_CATALOG.every((entry) => entry.promptMetadata !== undefined)).toBe(true);
  });

  it("serves the API catalog through sg://apis", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.apis)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(LIVE_API_CATALOG);
  });

  it("serves the tool catalog through sg://tools", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.tools)!();
    const payload = JSON.parse(result.contents[0]!.text!);

    expect(payload).toEqual(LIVE_TOOL_CATALOG);
    expect(payload.find((tool: { name: string }) => tool.name === "sg_query")).toMatchObject({
      name: "sg_query",
      title: "Query",
      surface: "canonical",
      preferred: true,
      annotations: expect.objectContaining({ readOnlyHint: true }),
      hasOutputSchema: true,
    });
  });

  it("serves the workflow catalog through sg://workflows", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.workflows)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(NORMALIZED_WORKFLOW_CATALOG);
  });

  it("serves the recipe catalog through sg://recipes", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.recipes)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(toSerializable(NORMALIZED_RECIPE_CATALOG));
  });

  it("serves the runtime catalog through sg://runtime", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.runtime)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(RUNTIME_CATALOG);
  });

  it("serves the playbook catalog through sg://playbooks", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.playbooks)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(toSerializable(NORMALIZED_PLAYBOOK_CATALOG));
  });

  it("serves the benchmark catalog through sg://benchmarks", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.benchmarks)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(BENCHMARK_CATALOG);
  });

  it("overlays sg://benchmarks with a CI snapshot override when configured", async () => {
    const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-benchmarks-"));
    const snapshotPath = join(tempDir, "snapshot.json");
    const snapshot = {
      schemaVersion: "2.0",
      generatedAt: "2026-03-30T12:00:00.000Z",
      source: "github-actions",
      commitSha: "abc123",
      runUrl: "https://github.com/example/repo/actions/runs/123",
      checks: [
        {
          name: "npm run verify",
          status: "passed",
          notes: "verify completed",
        },
      ],
      sloMeasurements: [
        {
          workflow: "Business Registry Diligence",
          availabilityPct: 99.1,
          latencyP50Ms: 900,
          latencyP95Ms: 1900,
          freshnessCompletenessPct: 100,
          measurementWindow: "rolling-7d",
          status: "within_slo",
          evidence: "ci smoke",
          notes: ["all checks passed"],
        },
      ],
    };

    writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2));
    const previous = process.env["SG_APIS_BENCHMARK_SNAPSHOT_PATH"];
    process.env["SG_APIS_BENCHMARK_SNAPSHOT_PATH"] = snapshotPath;

    try {
      const { resourceHandlers } = collectSurface();
      const result = await resourceHandlers.get(RESOURCE_URIS.benchmarks)!();
      const payload = JSON.parse(result.contents[0]!.text!);
      expect(payload.latestEvidenceSnapshot).toEqual(snapshot);
    } finally {
      if (previous === undefined) {
        delete process.env["SG_APIS_BENCHMARK_SNAPSHOT_PATH"];
      } else {
        process.env["SG_APIS_BENCHMARK_SNAPSHOT_PATH"] = previous;
      }
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it("serves the operations taxonomy through sg://ops-taxonomy", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.opsTaxonomy)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(OPS_TAXONOMY_CATALOG);
  });

  it("enriches workflow and recipe catalogs with trust metadata", () => {
    expect(WORKFLOW_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          name: "Civic Discovery",
          blockerFields: expect.arrayContaining(["directory", "postalCode", "name"]),
          continuationTools: expect.arrayContaining(["sg_msf_family_services", "sg_ecda_childcare_centres"]),
        }),
        expect.objectContaining({
          name: "Route Planning",
          authPrerequisites: expect.arrayContaining([expect.stringContaining("OneMap credentials")]),
        }),
        expect.objectContaining({
          id: "transport_status",
          outputShapeVersion: "transport-brief/v2",
        }),
        expect.objectContaining({
          id: "environment_snapshot",
          outputShapeVersion: "environment-brief/v2",
        }),
      ]),
    );
    expect(RECIPE_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          name: "Postal Route",
          blockerFields: ["originPostalCode", "destinationPostalCode"],
        }),
        expect.objectContaining({
          name: "Business Due Diligence",
          continuationTools: expect.arrayContaining(["sg_acra_entities", "sg_bca_registered_contractors"]),
        }),
        expect.objectContaining({
          name: "Architecture Firm Diligence",
          continuationTools: expect.arrayContaining(["sg_boa_architecture_firms", "sg_boa_architects"]),
        }),
        expect.objectContaining({
          name: "Healthcare Supplier Diligence",
          continuationTools: expect.arrayContaining(["sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies"]),
        }),
        expect.objectContaining({
          name: "Hotel Operator Lookup",
          continuationTools: expect.arrayContaining(["sg_hlb_hotels"]),
        }),
        expect.objectContaining({
          name: "MOE School Directory Lookup",
          continuationTools: expect.arrayContaining(["sg_moe_schools"]),
        }),
        expect.objectContaining({
          name: "MOH Healthcare Directory Lookup",
          continuationTools: expect.arrayContaining(["sg_moh_facilities"]),
        }),
        expect.objectContaining({
          id: "bus_stop_status",
          outputShapeVersion: "transport-brief/v2",
        }),
        expect.objectContaining({
          id: "outdoor_event_check",
          outputShapeVersion: "environment-brief/v2",
        }),
      ]),
    );
    expect(RUNTIME_CATALOG.queryStatusContract).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ status: "blocked", isError: false }),
        expect.objectContaining({ status: "unsupported", isError: false }),
        expect.objectContaining({ status: "failed", isError: true }),
      ]),
    );
    expect(PLAYBOOK_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "relocation_neighbourhood_brief",
          recommendedResources: expect.arrayContaining(["sg://recipes", "sg://runtime", "sg://benchmarks"]),
        }),
        expect.objectContaining({
          id: "business_opportunity_scan",
          directTools: expect.arrayContaining(["sg_business_dossier", "sg_gebiz_tenders", "sg_singstat_search"]),
        }),
        expect.objectContaining({
          id: "social_support_navigation",
          primaryWorkflows: expect.arrayContaining(["Civic Discovery"]),
        }),
      ]),
    );
    expect(BENCHMARK_CATALOG.workflowProfiles).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          workflow: "Business Registry Diligence",
          primaryCacheTier: "STATIC",
        }),
        expect.objectContaining({
          workflow: "Property And Regulatory Due Diligence",
          primaryCacheTier: "DAILY",
        }),
      ]),
    );
    expect(OPS_TAXONOMY_CATALOG.errorCodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "VALIDATION_ERROR", retryable: false, severity: "low" }),
        expect.objectContaining({ code: "EMPTY_RESULT", retryable: false, severity: "low" }),
        expect.objectContaining({ code: "TRANSIT_TRACE_NOT_FOUND", retryable: false, severity: "low" }),
        expect.objectContaining({ code: "TRACE_NOT_FOUND", retryable: false, severity: "low" }),
        expect.objectContaining({ code: "REQUEST_NOT_FOUND", retryable: false, severity: "low" }),
        expect.objectContaining({ code: "HTTP_4XX", retryable: false, severity: "low" }),
        expect.objectContaining({ code: "HTTP_5XX", retryable: true, severity: "high" }),
        expect.objectContaining({ code: "INTERNAL_ERROR", retryable: false, severity: "high" }),
      ]),
    );
    expect(OPS_TAXONOMY_CATALOG).toMatchObject({
      schemaVersion: "ops-taxonomy/v1",
      errorEnvelope: {
        contractVersion: "tool-error/v2",
      },
    });
  });
});
