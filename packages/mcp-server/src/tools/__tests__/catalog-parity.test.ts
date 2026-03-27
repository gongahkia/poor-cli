import { describe, expect, it } from "vitest";
import {
  API_CATALOG,
  BENCHMARK_CATALOG,
  PLAYBOOK_CATALOG,
  RECIPE_CATALOG,
  RESOURCE_URIS,
  RUNTIME_CATALOG,
  TOOL_CATALOG,
  WORKFLOW_CATALOG,
} from "../catalog.js";
import { registerAllTools } from "../registry.js";

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
    tool: (name: string) => {
      registeredTools.push(name);
    },
    resource: (_name: string, uri: string, handler: ResourceHandler) => {
      resourceHandlers.set(uri, handler);
    },
  };

  registerAllTools(server as unknown as Parameters<typeof registerAllTools>[0]);

  return { registeredTools, resourceHandlers };
};

describe("tool catalog parity", () => {
  it("contains exactly one entry for each registered public tool", () => {
    const { registeredTools } = collectSurface();
    const catalogNames = TOOL_CATALOG.map((tool) => tool.name);

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
    expect(API_CATALOG).toHaveLength(29);
    expect(TOOL_CATALOG).toHaveLength(68);
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
  it("serves the API catalog through sg://apis", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.apis)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(API_CATALOG);
  });

  it("serves the tool catalog through sg://tools", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.tools)!();
    const payload = JSON.parse(result.contents[0]!.text!);

    expect(payload).toEqual(TOOL_CATALOG);
    expect(payload.find((tool: { name: string }) => tool.name === "sg_query")).toMatchObject({
      name: "sg_query",
      surface: "canonical",
      preferred: true,
    });
  });

  it("serves the workflow catalog through sg://workflows", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.workflows)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(WORKFLOW_CATALOG);
  });

  it("serves the recipe catalog through sg://recipes", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.recipes)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(RECIPE_CATALOG);
  });

  it("serves the runtime catalog through sg://runtime", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.runtime)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(RUNTIME_CATALOG);
  });

  it("serves the playbook catalog through sg://playbooks", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.playbooks)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(PLAYBOOK_CATALOG);
  });

  it("serves the benchmark catalog through sg://benchmarks", async () => {
    const { resourceHandlers } = collectSurface();
    const result = await resourceHandlers.get(RESOURCE_URIS.benchmarks)!();

    expect(JSON.parse(result.contents[0]!.text!)).toEqual(BENCHMARK_CATALOG);
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
  });
});
