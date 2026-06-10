import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { attachLoggingBridge, type LoggingBridge } from "./logging.js";
import {
  buildServerIcons,
  SERVER_DESCRIPTION,
  SERVER_INSTRUCTIONS,
  SERVER_NAME,
  SERVER_TITLE,
  SERVER_VERSION,
  SERVER_WEBSITE_URL,
} from "./server-metadata.js";
import { registerAllTools } from "./tools/registry.js";
import type { ToolSet } from "./tools/tool-definition.js";

export type ServerFactoryOptions = {
  readonly enabledToolsets?: ReadonlySet<ToolSet>;
  readonly baseUrl?: URL;
};

export type ServerInstance = {
  readonly server: McpServer;
  readonly close: () => Promise<void>;
};

export const createServerInstance = (options?: ServerFactoryOptions): ServerInstance => {
  const server = new McpServer({
    name: SERVER_NAME,
    version: SERVER_VERSION,
    title: SERVER_TITLE,
    description: SERVER_DESCRIPTION,
    websiteUrl: SERVER_WEBSITE_URL,
    icons: buildServerIcons(options?.baseUrl),
  }, {
    capabilities: {
      logging: {},
    },
    instructions: SERVER_INSTRUCTIONS,
  });

  registerAllTools(server, options?.enabledToolsets === undefined ? undefined : { enabledToolsets: options.enabledToolsets });

  const loggingBridge: LoggingBridge = attachLoggingBridge(server);

  return {
    server,
    close: async () => {
      loggingBridge.close();
      await server.close().catch(() => undefined);
    },
  };
};
