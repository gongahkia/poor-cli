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
  it("contains exactly one entry for each registered CDD runtime tool", () => {
    const { registeredTools } = collectSurface();
    const catalogNames = LIVE_TOOL_CATALOG.map((tool) => tool.name);

    expect(new Set(catalogNames).size).toBe(catalogNames.length);
    expect(catalogNames.slice().sort()).toEqual(registeredTools.slice().sort());
    expect(catalogNames).toHaveLength(28);
    expect(catalogNames).toEqual(expect.arrayContaining(["sg_cdd_report", "sg_resolve_counterparty"]));
    expect(catalogNames).not.toEqual(
      expect.arrayContaining(["sg_property_brief", "sg_macro_brief", "sg_transport_brief", "sg_datagov_search"]),
    );
  });

  it("marks sg_query as the preferred canonical CDD interface", () => {
    expect(TOOL_CATALOG.find((tool) => tool.name === "sg_query")).toMatchObject({
      name: "sg_query",
      surface: "canonical",
      preferred: true,
    });
  });

  it("keeps CDD API catalog tool groups in sync with the registered surface", () => {
    const catalogNames = new Set(TOOL_CATALOG.map((tool) => tool.name));

    for (const api of API_CATALOG) {
      for (const toolName of api.tools) {
        expect(catalogNames.has(toolName)).toBe(true);
      }
    }

    expect(API_CATALOG).toHaveLength(11);
    expect(API_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: "CDD Query", tools: ["sg_query"] }),
        expect.objectContaining({ name: "Business Dossier", tools: ["sg_business_dossier"] }),
        expect.objectContaining({ name: "ACRA", tools: ["sg_acra_entities"] }),
        expect.objectContaining({ name: "BCA", tools: ["sg_bca_licensed_builders", "sg_bca_registered_contractors"] }),
        expect.objectContaining({ name: "BOA", tools: ["sg_boa_architects", "sg_boa_architecture_firms"] }),
        expect.objectContaining({ name: "CEA", tools: ["sg_cea_salespersons"] }),
        expect.objectContaining({ name: "GeBIZ", tools: ["sg_gebiz_tenders"] }),
        expect.objectContaining({ name: "HSA", tools: ["sg_hsa_licensed_pharmacies", "sg_hsa_health_product_licensees"] }),
        expect.objectContaining({ name: "HLB", tools: ["sg_hlb_hotels"] }),
        expect.objectContaining({ name: "External Diligence", tools: ["sg_sanctions_screen", "sg_opencorporates_links", "sg_adverse_media_lite", "sg_relationship_graph"] }),
      ]),
    );
    expect(API_CATALOG
      .filter((api) => api.name !== "Operations")
      .every((api) => api.preferredInterface === "sg_query")).toBe(true);
  });
});

describe("resource catalog parity", () => {
  it("keeps prompt metadata coverage in sync with every shipped CDD recipe and playbook", () => {
    expect(NORMALIZED_RECIPE_CATALOG.every((entry) => entry.promptMetadata !== undefined)).toBe(true);
    expect(NORMALIZED_PLAYBOOK_CATALOG.every((entry) => entry.promptMetadata !== undefined)).toBe(true);
  });

  it("keeps RECIPE_FALLBACK_TOOLS aligned with CDD recipes", async () => {
    const { RECIPE_FALLBACK_TOOLS } = await import("../recipe-fallbacks.js");
    for (const [recipeId, fallbackTools] of Object.entries(RECIPE_FALLBACK_TOOLS)) {
      const entry = NORMALIZED_RECIPE_CATALOG.find((candidate) => candidate.id === recipeId);
      expect(entry, `RECIPE_FALLBACK_TOOLS lists '${recipeId}' but no recipe with that id exists`).toBeDefined();
      expect(entry!.fallbackTools, `fallback tools for '${recipeId}' drifted from catalog`).toEqual(fallbackTools);
    }
  });

  it("serves CDD catalog resources", async () => {
    const { resourceHandlers } = collectSurface();

    expect(JSON.parse((await resourceHandlers.get(RESOURCE_URIS.apis)!()).contents[0]!.text!)).toEqual(LIVE_API_CATALOG);
    expect(JSON.parse((await resourceHandlers.get(RESOURCE_URIS.tools)!()).contents[0]!.text!)).toEqual(LIVE_TOOL_CATALOG);
    expect(JSON.parse((await resourceHandlers.get(RESOURCE_URIS.workflows)!()).contents[0]!.text!)).toEqual(NORMALIZED_WORKFLOW_CATALOG);
    expect(JSON.parse((await resourceHandlers.get(RESOURCE_URIS.recipes)!()).contents[0]!.text!)).toEqual(toSerializable(NORMALIZED_RECIPE_CATALOG));
    expect(JSON.parse((await resourceHandlers.get(RESOURCE_URIS.runtime)!()).contents[0]!.text!)).toEqual(RUNTIME_CATALOG);
    expect(JSON.parse((await resourceHandlers.get(RESOURCE_URIS.playbooks)!()).contents[0]!.text!)).toEqual(toSerializable(NORMALIZED_PLAYBOOK_CATALOG));
    expect(JSON.parse((await resourceHandlers.get(RESOURCE_URIS.benchmarks)!()).contents[0]!.text!)).toEqual(BENCHMARK_CATALOG);
    expect(JSON.parse((await resourceHandlers.get(RESOURCE_URIS.opsTaxonomy)!()).contents[0]!.text!)).toEqual(OPS_TAXONOMY_CATALOG);
  });

  it("overlays sg://benchmarks with a CI snapshot override when configured", async () => {
    const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-benchmarks-"));
    const snapshotPath = join(tempDir, "snapshot.json");
    const snapshot = {
      schemaVersion: "2.0",
      generatedAt: "2026-05-18T12:00:00.000Z",
      source: "github-actions",
      commitSha: "abc123",
      runUrl: "https://github.com/example/repo/actions/runs/123",
      checks: [
        { name: "npm run build", status: "passed", notes: "build completed" },
      ],
      sloMeasurements: [
        {
          workflow: "Company CDD Report",
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

  it("describes CDD-only workflow, recipe, playbook, and benchmark metadata", () => {
    expect(WORKFLOW_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "company_cdd_report",
          blockerFields: expect.arrayContaining(["entityName", "uen"]),
          continuationTools: expect.arrayContaining(["sg_gebiz_tenders", "sg_sanctions_screen"]),
          outputShapeVersion: "business-dossier/v1",
        }),
      ]),
    );
    expect(RECIPE_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "business_due_diligence",
          continuationTools: expect.arrayContaining(["sg_sanctions_screen", "sg_opencorporates_links"]),
        }),
        expect.objectContaining({ id: "architecture_firm_diligence" }),
        expect.objectContaining({ id: "healthcare_supplier_diligence" }),
        expect.objectContaining({ id: "hotel_operator_lookup" }),
      ]),
    );
    expect(PLAYBOOK_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "business_opportunity_scan",
          primaryWorkflows: expect.arrayContaining(["Company CDD Report"]),
          directTools: expect.arrayContaining(["sg_business_dossier", "sg_gebiz_tenders", "sg_acra_entities"]),
        }),
      ]),
    );
    expect(BENCHMARK_CATALOG.workflowProfiles).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          workflow: "Company CDD Report",
          primaryCacheTier: "STATIC + SUPPLEMENTAL",
        }),
      ]),
    );
    expect(RUNTIME_CATALOG.sourceUseWarnings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          api: "ACRA",
          warnings: expect.arrayContaining([expect.stringContaining("redistribution")]),
        }),
        expect.objectContaining({
          api: "External Diligence",
          warnings: expect.arrayContaining([expect.stringContaining("analyst review")]),
        }),
      ]),
    );
  });
});
