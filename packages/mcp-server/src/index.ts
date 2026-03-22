#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createLogger } from "@sg-apis/shared";
import { registerAllTools } from "./tools/registry.js";
import { closeCache } from "./middleware/cache-middleware.js";

const logger = createLogger("server");

const SHUTDOWN_TIMEOUT = 5000; // WHY: 5 seconds is enough for cache flush, prevents zombie processes

const server = new McpServer({
  name: "sg-apis-mcp",
  version: "0.1.0",
});

registerAllTools(server);

const gracefulShutdown = async (): Promise<void> => {
  logger.info("Shutting down...");

  const timeout = setTimeout(() => {
    logger.error("Shutdown timeout exceeded, forcing exit");
    process.exit(1);
  }, SHUTDOWN_TIMEOUT);

  try {
    closeCache();
    logger.info("Shutdown complete");
  } finally {
    clearTimeout(timeout);
    process.exit(0);
  }
};

process.on("SIGTERM", () => void gracefulShutdown());
process.on("SIGINT", () => void gracefulShutdown());

const main = async (): Promise<void> => {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  logger.info("sg-apis-mcp server started");
};

void main();
