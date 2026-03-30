#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createLogger } from "@sg-apis/shared";
import { warmCache } from "./cache/warm.js";
import { derivePublicHttpToolsets, HttpAuthController, type HttpAuthMode } from "./http-auth.js";
import { startHttpServer, isLocalHost } from "./http-server.js";
import { closeCache } from "./middleware/cache-middleware.js";
import { createServerInstance } from "./server-factory.js";
import { artifactStore } from "./tools/artifacts.js";
import type { ToolSet } from "./tools/tool-definition.js";

type TransportMode = "stdio" | "http";

const logger = createLogger("server");
const SHUTDOWN_TIMEOUT = 5000;
const ALL_TOOLSETS = ["public", "briefs", "query", "health", "ops"] as const satisfies readonly ToolSet[];

const readOption = (name: string): string | undefined => {
  const direct = process.argv.find((arg) => arg.startsWith(`--${name}=`));
  if (direct !== undefined) {
    return direct.slice(name.length + 3);
  }

  const index = process.argv.findIndex((arg) => arg === `--${name}`);
  if (index === -1) {
    return undefined;
  }

  return process.argv[index + 1];
};

const parseTransportMode = (): TransportMode => {
  const value = readOption("transport") ?? process.env["SG_APIS_TRANSPORT"] ?? "stdio";
  if (value !== "stdio" && value !== "http") {
    throw new Error(`Unsupported transport "${value}". Use stdio or http.`);
  }
  return value;
};

const parsePort = (): number => {
  const value = readOption("port") ?? process.env["SG_APIS_HTTP_PORT"] ?? process.env["PORT"] ?? "3000";
  const port = Number(value);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    throw new Error(`Invalid port "${value}".`);
  }
  return port;
};

const parseToolsets = (transportMode: TransportMode): ReadonlySet<ToolSet> => {
  const configured = readOption("toolsets") ?? process.env["SG_APIS_TOOLSETS"];
  if (configured === undefined || configured.trim() === "") {
    return new Set(
      transportMode === "http"
        ? (["public", "briefs", "query", "health"] as const)
        : ALL_TOOLSETS,
    );
  }

  const toolsets = configured
    .split(",")
    .map((value) => value.trim())
    .filter((value): value is ToolSet => ALL_TOOLSETS.includes(value as ToolSet));

  if (toolsets.length === 0) {
    throw new Error(`No valid toolsets found in "${configured}".`);
  }

  return new Set(toolsets);
};

const parseHttpAuthMode = (host: string): HttpAuthMode => {
  const configured = readOption("http-auth-mode") ?? process.env["SG_APIS_HTTP_AUTH_MODE"];
  if (configured === undefined || configured.trim() === "") {
    return isLocalHost(host) ? "none" : "mixed";
  }

  if (configured !== "none" && configured !== "mixed" && configured !== "all") {
    throw new Error(`Unsupported HTTP auth mode "${configured}". Use none, mixed, or all.`);
  }

  return configured;
};

const parseRequiredScopes = (): readonly string[] => {
  const configured = process.env["SG_APIS_OIDC_REQUIRED_SCOPES"];
  if (configured === undefined || configured.trim() === "") {
    return [];
  }
  return configured.split(",").map((scope) => scope.trim()).filter((scope) => scope !== "");
};

const parseClockSkewSec = (): number => {
  const configured = process.env["SG_APIS_OIDC_CLOCK_SKEW_SEC"] ?? "60";
  const value = Number(configured);
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`Invalid SG_APIS_OIDC_CLOCK_SKEW_SEC value "${configured}".`);
  }
  return value;
};

let shutdownHandler: (() => Promise<void>) | undefined;

const gracefulShutdown = async (): Promise<void> => {
  logger.info("Shutting down...");

  const timeout = setTimeout(() => {
    logger.error("Shutdown timeout exceeded, forcing exit");
    process.exit(1);
  }, SHUTDOWN_TIMEOUT);

  try {
    closeCache();
    artifactStore.close();
    await shutdownHandler?.();
    logger.info("Shutdown complete");
  } finally {
    clearTimeout(timeout);
    process.exit(0);
  }
};

process.on("SIGTERM", () => void gracefulShutdown());
process.on("SIGINT", () => void gracefulShutdown());
process.on("unhandledRejection", (reason) => {
  logger.error("Unhandled promise rejection", { reason });
});
process.on("uncaughtException", (error) => {
  logger.error("Uncaught exception", { error });
  process.exit(1);
});

const main = async (): Promise<void> => {
  const transportMode = parseTransportMode();
  const enabledToolsets = parseToolsets(transportMode);

  if (transportMode === "http") {
    const host = readOption("host") ?? process.env["SG_APIS_HTTP_HOST"] ?? "127.0.0.1";
    const port = parsePort();
    const authMode = parseHttpAuthMode(host);
    const issuer = process.env["SG_APIS_OIDC_ISSUER"];
    const audience = process.env["SG_APIS_OIDC_AUDIENCE"];
    const remoteBaseUrl = process.env["SG_APIS_REMOTE_BASE_URL"];
    const hasExplicitRemoteBaseUrl = remoteBaseUrl !== undefined && remoteBaseUrl.trim() !== "";

    if ((authMode === "mixed" || authMode === "all") && ((issuer ?? "").trim() === "" || (audience ?? "").trim() === "")) {
      throw new Error(`HTTP auth mode "${authMode}" requires SG_APIS_OIDC_ISSUER and SG_APIS_OIDC_AUDIENCE.`);
    }

    const resourceServerUrl = hasExplicitRemoteBaseUrl
      ? new URL(remoteBaseUrl!)
      : new URL(`http://${host}:${port}/mcp`);

    const auth = new HttpAuthController({
      mode: authMode,
      ...(issuer === undefined || issuer.trim() === "" ? {} : { issuer }),
      ...(audience === undefined || audience.trim() === "" ? {} : { audience }),
      ...(process.env["SG_APIS_OIDC_JWKS_URI"] === undefined || process.env["SG_APIS_OIDC_JWKS_URI"]?.trim() === ""
        ? {}
        : { jwksUri: process.env["SG_APIS_OIDC_JWKS_URI"] }),
      requiredScopes: parseRequiredScopes(),
      clockSkewSec: parseClockSkewSec(),
      resourceServerUrl,
      fullToolsets: enabledToolsets,
      publicToolsets: derivePublicHttpToolsets(enabledToolsets),
      logger,
    });

    const httpServer = await startHttpServer({
      host,
      port,
      auth,
      useBoundResourceServerUrl: !hasExplicitRemoteBaseUrl,
      logger,
    });

    shutdownHandler = async () => {
      await httpServer.close();
    };

    logger.info("sg-apis-mcp HTTP server started", {
      host,
      port,
      transport: transportMode,
      toolsets: [...enabledToolsets],
      authMode,
      publicToolsets: [...auth.publicToolsets],
      resourceServerUrl: auth.resourceServerUrl.href,
    });
  } else {
    const instance = createServerInstance({ enabledToolsets });
    const transport = new StdioServerTransport();
    await instance.server.connect(transport);

    shutdownHandler = async () => {
      await instance.close();
    };

    logger.info("sg-apis-mcp stdio server started", {
      transport: transportMode,
      toolsets: [...enabledToolsets],
    });
  }

  void warmCache().catch((error: unknown) => {
    logger.warn("cache warm-up failed", {
      error: error instanceof Error ? error.message : String(error),
    });
  });
};

void main().catch((error: unknown) => {
  logger.error("Server startup failed", { error });
  process.exit(1);
});
