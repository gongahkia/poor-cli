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
  it("contains exactly one entry for each registered Swee SG runtime tool", () => {
    const { registeredTools } = collectSurface();
    const catalogNames = LIVE_TOOL_CATALOG.map((tool) => tool.name);

    expect(new Set(catalogNames).size).toBe(catalogNames.length);
    expect(catalogNames.slice().sort()).toEqual(registeredTools.slice().sort());
    expect(catalogNames.length).toBeGreaterThan(50);
    expect(catalogNames).toEqual(expect.arrayContaining(["swee_pulse_snapshot", "swee_shield_audit_lookup", "sg_datagov_search"]));
    expect(catalogNames).not.toEqual(
      expect.arrayContaining(["sg_query", "sg_business_dossier", "sg_cdd_report", "sg_resolve_counterparty"]),
    );
  });

  it("marks Swee Pulse as the preferred canonical interface", () => {
    expect(TOOL_CATALOG.find((tool) => tool.name === "swee_pulse_snapshot")).toMatchObject({
      name: "swee_pulse_snapshot",
      surface: "canonical",
      preferred: true,
    });
  });

  it("keeps Swee SG API catalog tool groups in sync with the registered surface", () => {
    const catalogNames = new Set(TOOL_CATALOG.map((tool) => tool.name));

    for (const api of API_CATALOG) {
      for (const toolName of api.tools) {
        expect(catalogNames.has(toolName)).toBe(true);
      }
    }

    expect(API_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: "Swee Pulse", preferredInterface: "swee_pulse_snapshot" }),
        expect.objectContaining({ name: "Swee Shield", preferredInterface: "swee_shield_audit_lookup" }),
        expect.objectContaining({ name: "Mobility Sources" }),
        expect.objectContaining({ name: "Weather Sources" }),
        expect.objectContaining({ name: "Singapore Public Data Sources" }),
      ]),
    );
  });
});

describe("resource catalog parity", () => {
  it("keeps prompt metadata coverage in sync with every shipped recipe and playbook", () => {
    expect(NORMALIZED_RECIPE_CATALOG.every((entry) => entry.promptMetadata !== undefined)).toBe(true);
    expect(NORMALIZED_PLAYBOOK_CATALOG.every((entry) => entry.promptMetadata !== undefined)).toBe(true);
  });

  it("keeps RECIPE_FALLBACK_TOOLS aligned with shipped recipes", async () => {
    const { RECIPE_FALLBACK_TOOLS } = await import("../recipe-fallbacks.js");
    for (const [recipeId, fallbackTools] of Object.entries(RECIPE_FALLBACK_TOOLS)) {
      const entry = NORMALIZED_RECIPE_CATALOG.find((candidate) => candidate.id === recipeId);
      expect(entry, `RECIPE_FALLBACK_TOOLS lists '${recipeId}' but no recipe with that id exists`).toBeDefined();
      expect(entry!.fallbackTools, `fallback tools for '${recipeId}' drifted from catalog`).toEqual(fallbackTools);
    }
  });

  it("serves Swee SG catalog resources", async () => {
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
          workflow: "Swee Pulse Snapshot",
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

  it("describes Swee Pulse, Shield, playbook, and benchmark metadata", () => {
    expect(WORKFLOW_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "pulse_snapshot",
          blockerFields: expect.arrayContaining(["sourceHealth", "gaps"]),
          fallbackTools: expect.arrayContaining(["swee_pulse_mobility", "swee_pulse_weather"]),
          outputShapeVersion: "pulse-snapshot/v1",
        }),
      ]),
    );
    expect(RECIPE_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "pulse_overview",
          fallbackTools: expect.arrayContaining(["swee_pulse_mobility", "swee_pulse_weather"]),
        }),
        expect.objectContaining({ id: "shield_recent_audit" }),
      ]),
    );
    expect(PLAYBOOK_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "city_ops",
          primaryWorkflows: expect.arrayContaining(["Swee Pulse Snapshot", "Swee Shield Audit Review"]),
          directTools: expect.arrayContaining(["swee_pulse_snapshot", "swee_shield_audit_lookup"]),
        }),
      ]),
    );
    expect(BENCHMARK_CATALOG.workflowProfiles).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          workflow: "Swee Pulse Snapshot",
          primaryCacheTier: "REALTIME + STATIC",
        }),
      ]),
    );
    expect(RUNTIME_CATALOG).toMatchObject({
      schemaVersion: "swee-runtime/v1",
      pulseContract: expect.stringContaining("Signals are deterministic"),
    });
  });
});
