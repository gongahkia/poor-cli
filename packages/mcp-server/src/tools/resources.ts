import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  API_CATALOG,
  BENCHMARK_CATALOG,
  PLAYBOOK_CATALOG,
  RUNTIME_CATALOG,
  RECIPE_CATALOG,
  RESOURCE_URIS,
  TOOL_CATALOG,
  WORKFLOW_CATALOG,
} from "./catalog.js";

export const registerResources = (server: McpServer): void => {
  server.resource("sg-apis", RESOURCE_URIS.apis, async () => ({
    contents: [
      {
        uri: RESOURCE_URIS.apis,
        text: JSON.stringify(API_CATALOG, null, 2),
        mimeType: "application/json",
      },
    ],
  }));

  server.resource("sg-tools", RESOURCE_URIS.tools, async () => ({
    contents: [
      {
        uri: RESOURCE_URIS.tools,
        text: JSON.stringify(TOOL_CATALOG, null, 2),
        mimeType: "application/json",
      },
    ],
  }));

  server.resource("sg-workflows", RESOURCE_URIS.workflows, async () => ({
    contents: [
      {
        uri: RESOURCE_URIS.workflows,
        text: JSON.stringify(WORKFLOW_CATALOG, null, 2),
        mimeType: "application/json",
      },
    ],
  }));

  server.resource("sg-recipes", RESOURCE_URIS.recipes, async () => ({
    contents: [
      {
        uri: RESOURCE_URIS.recipes,
        text: JSON.stringify(RECIPE_CATALOG, null, 2),
        mimeType: "application/json",
      },
    ],
  }));

  server.resource("sg-runtime", RESOURCE_URIS.runtime, async () => ({
    contents: [
      {
        uri: RESOURCE_URIS.runtime,
        text: JSON.stringify(RUNTIME_CATALOG, null, 2),
        mimeType: "application/json",
      },
    ],
  }));

  server.resource("sg-playbooks", RESOURCE_URIS.playbooks, async () => ({
    contents: [
      {
        uri: RESOURCE_URIS.playbooks,
        text: JSON.stringify(PLAYBOOK_CATALOG, null, 2),
        mimeType: "application/json",
      },
    ],
  }));

  server.resource("sg-benchmarks", RESOURCE_URIS.benchmarks, async () => ({
    contents: [
      {
        uri: RESOURCE_URIS.benchmarks,
        text: JSON.stringify(BENCHMARK_CATALOG, null, 2),
        mimeType: "application/json",
      },
    ],
  }));
};
