import { describe, expect, it } from "vitest";
import {
  API_CATALOG,
  RESOURCE_URIS,
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
    expect(API_CATALOG).toHaveLength(11);
    expect(TOOL_CATALOG).toHaveLength(47);
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
      ]),
    );
    expect(TOOL_CATALOG).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: "sg_acra_entities", surface: "canonical" }),
        expect.objectContaining({ name: "sg_cea_salespersons", surface: "canonical" }),
        expect.objectContaining({ name: "sg_bca_licensed_builders", surface: "canonical" }),
        expect.objectContaining({ name: "sg_bca_registered_contractors", surface: "canonical" }),
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
});
