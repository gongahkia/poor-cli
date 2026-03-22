import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_CATALOG, RESOURCE_URIS, TOOL_CATALOG, WORKFLOW_CATALOG } from "./catalog.js";

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
};
