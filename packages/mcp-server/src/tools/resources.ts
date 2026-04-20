import { readFileSync } from "node:fs";
import { ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { Variables } from "@modelcontextprotocol/sdk/shared/uriTemplate.js";
import { registerAppResource, RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/server";
import {
  BENCHMARK_CATALOG,
  buildBenchmarkCatalog,
  type BenchmarkEvidenceSnapshot,
  OPS_TAXONOMY_CATALOG,
  RESOURCE_URIS,
  RUNTIME_CATALOG,
} from "./catalog.js";
import { artifactStore, serializeArtifactEntry } from "./artifacts.js";
import {
  NORMALIZED_PLAYBOOK_CATALOG,
  NORMALIZED_RECIPE_CATALOG,
  NORMALIZED_WORKFLOW_CATALOG,
  buildApiCatalog,
  buildToolCatalog,
  getApiCatalogEntry,
  getRecipeCatalogEntry,
  getToolCatalogEntry,
  getWorkflowCatalogEntry,
} from "./catalog-surface.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { MAP_UI_RESOURCE_URI } from "./map-payload.js";

const JSON_MIME_TYPE = "application/json";

const DEFAULT_RESOURCE_ANNOTATIONS: {
  audience: ("assistant" | "user")[];
  priority: number;
} = {
  audience: ["assistant", "user"],
  priority: 0.9,
};

const MAP_UI_RESOURCE_META = {
  ui: {
    prefersBorder: true,
    csp: {
      resourceDomains: [
        "https://unpkg.com",
        "https://*.tile.openstreetmap.org",
      ],
    },
  },
} as const;

const toJsonContents = (uri: string, payload: unknown) => ({
  contents: [
    {
      uri,
      text: JSON.stringify(payload, null, 2),
      mimeType: JSON_MIME_TYPE,
    },
  ],
});

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> => {
  return typeof value === "object" && value !== null;
};

const toBenchmarkSnapshot = (value: unknown): BenchmarkEvidenceSnapshot | null => {
  if (!isRecord(value)) {
    return null;
  }

  if (value["schemaVersion"] !== "1.0" && value["schemaVersion"] !== "2.0") {
    return null;
  }

  if (typeof value["generatedAt"] !== "string" || typeof value["source"] !== "string" || typeof value["commitSha"] !== "string") {
    return null;
  }

  if (value["source"] !== "repository-baseline" && value["source"] !== "github-actions" && value["source"] !== "local") {
    return null;
  }

  if (value["runUrl"] !== null && typeof value["runUrl"] !== "string") {
    return null;
  }

  if (!Array.isArray(value["checks"])) {
    return null;
  }

  const checks = value["checks"].every((entry) => (
    isRecord(entry)
    && typeof entry["name"] === "string"
    && typeof entry["notes"] === "string"
    && (entry["status"] === "passed" || entry["status"] === "skipped")
  ));

  if (!checks) {
    return null;
  }

  if (value["sloMeasurements"] === undefined) {
    return value as BenchmarkEvidenceSnapshot;
  }

  if (!Array.isArray(value["sloMeasurements"])) {
    return null;
  }

  const measurementsValid = value["sloMeasurements"].every((entry) => (
    isRecord(entry)
    && typeof entry["workflow"] === "string"
    && typeof entry["availabilityPct"] === "number"
    && typeof entry["latencyP50Ms"] === "number"
    && typeof entry["latencyP95Ms"] === "number"
    && typeof entry["freshnessCompletenessPct"] === "number"
    && typeof entry["measurementWindow"] === "string"
    && typeof entry["evidence"] === "string"
    && (entry["status"] === "within_slo" || entry["status"] === "warning" || entry["status"] === "breach")
    && Array.isArray(entry["notes"])
    && entry["notes"].every((note) => typeof note === "string")
  ));

  return measurementsValid ? value as BenchmarkEvidenceSnapshot : null;
};

const readBenchmarkSnapshotOverride = (): BenchmarkEvidenceSnapshot | null => {
  const snapshotPath = process.env["SG_APIS_BENCHMARK_SNAPSHOT_PATH"];
  if (snapshotPath === undefined || snapshotPath.trim() === "") {
    return null;
  }

  try {
    const parsed = JSON.parse(readFileSync(snapshotPath, "utf8")) as unknown;
    return toBenchmarkSnapshot(parsed);
  } catch {
    return null;
  }
};

const getBenchmarkCatalogPayload = () => {
  const override = readBenchmarkSnapshotOverride();
  return override === null ? BENCHMARK_CATALOG : buildBenchmarkCatalog(override);
};

const buildVariableCompletion = (values: readonly string[]) => {
  return (value: string): string[] => values.filter((candidate) => candidate.startsWith(value));
};

const buildItemResource = (
  baseUri: string,
  id: string,
  title: string,
  description: string,
) => ({
  uri: `${baseUri}/${id}`,
  name: `${baseUri.replace("sg://", "sg-")}-${id}`,
  title,
  description,
  mimeType: JSON_MIME_TYPE,
  annotations: DEFAULT_RESOURCE_ANNOTATIONS,
});

const buildApiResources = (definitions: readonly RegisteredToolDefinition[]) => {
  return buildApiCatalog(definitions).map((entry) =>
    buildItemResource(RESOURCE_URIS.apis, entry.id, entry.name, entry.description),
  );
};

const buildToolResources = (definitions: readonly RegisteredToolDefinition[]) => {
  return buildToolCatalog(definitions).map((entry) =>
    buildItemResource(RESOURCE_URIS.tools, entry.name, entry.title ?? entry.name, entry.description),
  );
};

const buildWorkflowResources = () => {
  return NORMALIZED_WORKFLOW_CATALOG.map((entry) =>
    buildItemResource(RESOURCE_URIS.workflows, entry.id, entry.name, entry.intent),
  );
};

const buildRecipeResources = () => {
  return NORMALIZED_RECIPE_CATALOG.map((entry) =>
    buildItemResource(RESOURCE_URIS.recipes, entry.id, entry.name, entry.goal),
  );
};

const readSingleCatalogEntry = <T extends { readonly id: string }>(
  entry: T | undefined,
  uri: string,
) => {
  return toJsonContents(uri, entry ?? null);
};

const getVariable = (variables: Variables, key: string): string => {
  const value = variables[key];
  return typeof value === "string" ? value : "";
};

const MAP_PREVIEW_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Singapore Map Preview</title>
    <link
      rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
      crossorigin=""
    />
    <style>
      :root {
        color-scheme: light;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        background: #f7f1e3;
        color: #1f2937;
      }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        grid-template-rows: auto 1fr;
        background:
          radial-gradient(circle at top left, rgba(220, 38, 38, 0.12), transparent 32%),
          linear-gradient(180deg, #f7f1e3 0%, #fffdf7 100%);
      }
      header {
        padding: 16px 20px 8px;
      }
      h1 {
        margin: 0 0 4px;
        font-size: 1.05rem;
      }
      p {
        margin: 0;
        font-size: 0.9rem;
        color: #4b5563;
      }
      #status {
        padding: 0 20px 12px;
        font-size: 0.85rem;
        color: #6b7280;
      }
      #map {
        min-height: 360px;
        margin: 0 20px 20px;
        border-radius: 18px;
        overflow: hidden;
        box-shadow: 0 18px 32px rgba(15, 118, 110, 0.12);
      }
      .legend {
        position: absolute;
        right: 16px;
        bottom: 16px;
        z-index: 500;
        padding: 10px 12px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(12px);
        font-size: 0.8rem;
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
      }
      .legend ul {
        margin: 8px 0 0;
        padding-left: 16px;
      }
    </style>
  </head>
  <body>
    <header>
      <h1>Singapore Map Preview</h1>
      <p>Read-only spatial preview for geocode, route, and neighbourhood workflows.</p>
    </header>
    <div id="status">Waiting for map payload…</div>
    <div id="map"></div>
    <script
      src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
      integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
      crossorigin=""
    ></script>
    <script>
      const statusEl = document.getElementById("status");
      const map = L.map("map", { zoomControl: true });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map);
      const layerGroup = L.layerGroup().addTo(map);

      const renderPayload = (payload) => {
        layerGroup.clearLayers();
        if (!payload || !Array.isArray(payload.markers)) {
          statusEl.textContent = "No map payload available for this result.";
          map.setView([1.3521, 103.8198], 11);
          return;
        }

        payload.markers.forEach((marker) => {
          const leafletMarker = L.marker([marker.lat, marker.lng]).addTo(layerGroup);
          leafletMarker.bindPopup("<strong>" + marker.label + "</strong>" + (marker.description ? "<br/>" + marker.description : ""));
        });

        if (Array.isArray(payload.polylines)) {
          payload.polylines.forEach((polyline) => {
            const latLngs = (polyline.coordinates || []).map((point) => [point.lat, point.lng]);
            if (latLngs.length >= 2) {
              L.polyline(latLngs, {
                color: polyline.approximate ? "#dc2626" : "#0f766e",
                weight: 4,
                opacity: 0.85,
                dashArray: polyline.approximate ? "8 6" : undefined,
              }).addTo(layerGroup);
            }
          });
        }

        if (payload.bounds) {
          map.fitBounds([
            [payload.bounds.south, payload.bounds.west],
            [payload.bounds.north, payload.bounds.east],
          ], { padding: [24, 24] });
        } else if (payload.markers[0]) {
          map.setView([payload.markers[0].lat, payload.markers[0].lng], 15);
        } else {
          map.setView([1.3521, 103.8198], 11);
        }

        const legend = document.createElement("div");
        legend.className = "legend";
        legend.innerHTML = "<strong>Legend</strong>";
        if (Array.isArray(payload.legend) && payload.legend.length > 0) {
          const list = document.createElement("ul");
          payload.legend.forEach((entry) => {
            const item = document.createElement("li");
            item.textContent = entry.approximate ? entry.label + " (approximate)" : entry.label;
            list.appendChild(item);
          });
          legend.appendChild(list);
        }
        map.getContainer().querySelectorAll(".legend").forEach((node) => node.remove());
        map.getContainer().appendChild(legend);
        const hasApproximateRoute = Array.isArray(payload.polylines) && payload.polylines.some((polyline) => polyline.approximate);
        statusEl.textContent = payload.sourceTool
          ? "Source tool: " + payload.sourceTool + (hasApproximateRoute ? " (route line is approximate)" : "")
          : (hasApproximateRoute ? "Map preview ready. Route line is approximate." : "Map preview ready.");
      };

      window.addEventListener("message", (event) => {
        const payload = event && event.data && event.data.mapPayload
          ? event.data.mapPayload
          : event && event.data && event.data.structuredContent && event.data.structuredContent.mapPayload
            ? event.data.structuredContent.mapPayload
            : null;
        if (payload) {
          renderPayload(payload);
        }
      });

      renderPayload(window.__MCP_RESULT__ && window.__MCP_RESULT__.structuredContent
        ? window.__MCP_RESULT__.structuredContent.mapPayload
        : window.__MCP_RESULT__ && window.__MCP_RESULT__.mapPayload
          ? window.__MCP_RESULT__.mapPayload
          : null);
    </script>
  </body>
</html>`;

export const registerResources = (
  server: McpServer,
  definitions: readonly RegisteredToolDefinition[],
): void => {
  const apiCatalog = buildApiCatalog(definitions);
  const toolCatalog = buildToolCatalog(definitions);

  server.registerResource("sg-apis", RESOURCE_URIS.apis, {
    title: "API Catalog",
    description: "Public API families currently exposed by this server instance.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async () => toJsonContents(RESOURCE_URIS.apis, apiCatalog));

  server.registerResource("sg-tools", RESOURCE_URIS.tools, {
    title: "Tool Catalog",
    description: "Currently exposed sg_* tool catalog with MCP metadata.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async () => toJsonContents(RESOURCE_URIS.tools, toolCatalog));

  server.registerResource("sg-workflows", RESOURCE_URIS.workflows, {
    title: "Workflow Catalog",
    description: "Bounded workflow catalog with stable IDs and continuation hints.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async () => toJsonContents(RESOURCE_URIS.workflows, NORMALIZED_WORKFLOW_CATALOG));

  server.registerResource("sg-recipes", RESOURCE_URIS.recipes, {
    title: "Recipe Catalog",
    description: "Recipe catalog with stable IDs used by prompt discovery and bounded workflow entry.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async () => toJsonContents(RESOURCE_URIS.recipes, NORMALIZED_RECIPE_CATALOG));

  server.registerResource("sg-runtime", RESOURCE_URIS.runtime, {
    title: "Runtime Contract",
    description: "Live runtime contract for auth, latency, cache, health, and release expectations.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async () => toJsonContents(RESOURCE_URIS.runtime, RUNTIME_CATALOG));

  server.registerResource("sg-playbooks", RESOURCE_URIS.playbooks, {
    title: "Playbook Catalog",
    description: "Persona-oriented playbook catalog for common bounded workflow bundles.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async () => toJsonContents(RESOURCE_URIS.playbooks, NORMALIZED_PLAYBOOK_CATALOG));

  server.registerResource("sg-benchmarks", RESOURCE_URIS.benchmarks, {
    title: "Benchmark Catalog",
    description: "Integration and release-readiness expectations for the public MCP surface.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async () => toJsonContents(RESOURCE_URIS.benchmarks, getBenchmarkCatalogPayload()));

  server.registerResource("sg-ops-taxonomy", RESOURCE_URIS.opsTaxonomy, {
    title: "Operations Taxonomy",
    description: "Machine-readable error, retryability, and severity taxonomy for operational handling.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async () => toJsonContents(RESOURCE_URIS.opsTaxonomy, OPS_TAXONOMY_CATALOG));

  registerAppResource(server, "Singapore Map Preview UI", MAP_UI_RESOURCE_URI, {
    title: "Singapore Map Preview UI",
    description: "Read-only map preview template for geospatial sg_* tool outputs.",
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
    _meta: MAP_UI_RESOURCE_META,
  }, async () => ({
    contents: [
      {
        uri: MAP_UI_RESOURCE_URI,
        text: MAP_PREVIEW_HTML,
        mimeType: RESOURCE_MIME_TYPE,
      },
    ],
    _meta: MAP_UI_RESOURCE_META,
  }));

  server.registerResource("sg-api", new ResourceTemplate(`${RESOURCE_URIS.apis}/{name}`, {
    list: async () => ({ resources: buildApiResources(definitions) }),
    complete: {
      name: buildVariableCompletion(apiCatalog.map((entry) => entry.id)),
    },
  }), {
    title: "API Entry",
    description: "A single API family entry from the public API catalog.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async (_uri: URL, variables: Variables) => {
    const id = getVariable(variables, "name");
    return readSingleCatalogEntry(getApiCatalogEntry(id), `${RESOURCE_URIS.apis}/${id}`);
  });

  server.registerResource("sg-tool", new ResourceTemplate(`${RESOURCE_URIS.tools}/{name}`, {
    list: async () => ({ resources: buildToolResources(definitions) }),
    complete: {
      name: buildVariableCompletion(toolCatalog.map((entry) => entry.name)),
    },
  }), {
    title: "Tool Entry",
    description: "A single sg_* tool entry from the currently exposed tool catalog.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async (_uri: URL, variables: Variables) => {
    const name = getVariable(variables, "name");
    return toJsonContents(`${RESOURCE_URIS.tools}/${name}`, getToolCatalogEntry(definitions, name) ?? null);
  });

  server.registerResource("sg-workflow", new ResourceTemplate(`${RESOURCE_URIS.workflows}/{id}`, {
    list: async () => ({ resources: buildWorkflowResources() }),
    complete: {
      id: buildVariableCompletion(NORMALIZED_WORKFLOW_CATALOG.map((entry) => entry.id)),
    },
  }), {
    title: "Workflow Entry",
    description: "A single normalized workflow entry from the workflow catalog.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async (_uri: URL, variables: Variables) => {
    const id = getVariable(variables, "id");
    return readSingleCatalogEntry(getWorkflowCatalogEntry(id), `${RESOURCE_URIS.workflows}/${id}`);
  });

  server.registerResource("sg-recipe", new ResourceTemplate(`${RESOURCE_URIS.recipes}/{id}`, {
    list: async () => ({ resources: buildRecipeResources() }),
    complete: {
      id: buildVariableCompletion(NORMALIZED_RECIPE_CATALOG.map((entry) => entry.id)),
    },
  }), {
    title: "Recipe Entry",
    description: "A single normalized recipe entry from the recipe catalog.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async (_uri: URL, variables: Variables) => {
    const id = getVariable(variables, "id");
    return readSingleCatalogEntry(getRecipeCatalogEntry(id), `${RESOURCE_URIS.recipes}/${id}`);
  });

  server.registerResource("sg-artifact", new ResourceTemplate(`${RESOURCE_URIS.artifacts}/{kind}/{id}`, {
    list: undefined,
  }), {
    title: "Artifact Entry",
    description: "Transient JSON artifact generated for large tool outputs.",
    mimeType: JSON_MIME_TYPE,
    annotations: DEFAULT_RESOURCE_ANNOTATIONS,
  }, async (_uri: URL, variables: Variables) => {
    const kind = getVariable(variables, "kind");
    const id = getVariable(variables, "id");
    const uri = `${RESOURCE_URIS.artifacts}/${kind}/${id}`;
    const entry = artifactStore.read(uri);
    if (entry === null) {
      throw new Error(`Artifact not found or expired: ${uri}`);
    }
    return toJsonContents(uri, serializeArtifactEntry(entry));
  });
};
