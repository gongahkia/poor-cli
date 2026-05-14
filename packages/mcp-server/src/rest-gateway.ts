#!/usr/bin/env node
// REST gateway: exposes sg_* tools as HTTP POST endpoints
// usage: node packages/mcp-server/dist/rest-gateway.js
// env: PORT (default 3000), SG_APIS_TOOLSETS, SG_APIS_TOOL_PROFILE (default public profile)
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { randomUUID } from "node:crypto";
import { createLogger } from "@sg-apis/shared";
import { searchAcraEntitySuggestions } from "./apis/acra/client.js";
import { getWebPresence, isTinyFishSearchConfigured } from "./apis/tinyfish/client.js";
import { ALL_TOOL_DEFINITIONS } from "./tools/tool-set.js";
import { isToolEnabled } from "./tools/tool-metadata.js";
const PORT = Number(process.env["PORT"] ?? 3000);
const DEFAULT_DEV_WEB_ORIGIN = "http://localhost:5173";
const logger = createLogger("rest-gateway");
import { resolveEnabledToolsets } from "./tools/toolset-profiles.js";

const configuredToolsets = process.env["SG_APIS_TOOLSETS"];
const configuredProfile = process.env["SG_APIS_TOOL_PROFILE"];
const enabledToolsets = resolveEnabledToolsets({
  transportMode: "http",
  ...(configuredToolsets === undefined ? {} : { configuredToolsets }),
  ...(configuredProfile === undefined ? {} : { configuredProfile }),
});
const enabledTools = ALL_TOOL_DEFINITIONS.filter((t) => isToolEnabled(t, enabledToolsets));
const toolMap = new Map(enabledTools.map((t) => [t.name, t]));
const allowedCorsOrigins = new Set(
  (process.env["DUDE_WEB_ORIGIN_ALLOWLIST"] ??
    (process.env["NODE_ENV"] === "production" ? "" : DEFAULT_DEV_WEB_ORIGIN))
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
);

logger.info("gateway started", { toolsets: [...enabledToolsets], tools: enabledTools.length, total: ALL_TOOL_DEFINITIONS.length });

const readBody = (req: IncomingMessage): Promise<string> =>
  new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });

const sendJson = (res: ServerResponse, status: number, body: unknown): void => {
  res.writeHead(status);
  res.end(JSON.stringify(body));
};

const getQueryValue = (url: URL, key: string): string => url.searchParams.get(key)?.trim() ?? "";

const summarizeBusinessInput = (input: unknown): Record<string, unknown> => {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    return {};
  }
  const record = input as Record<string, unknown>;
  return {
    ...(typeof record["uen"] === "string" ? { uen: record["uen"] } : {}),
    ...(typeof record["entityName"] === "string" ? { entityName: record["entityName"] } : {}),
  };
};

const summarizeBusinessDossier = (record: unknown): Record<string, unknown> => {
  if (record === null || typeof record !== "object" || Array.isArray(record)) {
    return {};
  }
  const dossier = record as {
    readonly gaps?: readonly { readonly code?: string }[];
    readonly records?: {
      readonly resolution?: {
        readonly matchedModules?: readonly string[];
        readonly unmatchedModules?: readonly string[];
      };
    };
  };
  const gaps = dossier.gaps ?? [];
  return {
    matchedModules: dossier.records?.resolution?.matchedModules ?? [],
    unmatchedModules: dossier.records?.resolution?.unmatchedModules ?? [],
    gapCodes: gaps.map((gap) => gap.code).filter(Boolean),
    upstreamFailures: gaps
      .map((gap) => gap.code)
      .filter((code): code is string => typeof code === "string" && code.includes("UNAVAILABLE")),
  };
};

const getOrigin = (req: IncomingMessage): string | undefined => {
  const origin = req.headers.origin;
  return typeof origin === "string" ? origin : undefined;
};

const applyCorsHeaders = (req: IncomingMessage, res: ServerResponse): boolean => {
  const origin = getOrigin(req);
  if (!origin || !allowedCorsOrigins.has(origin)) {
    return false;
  }

  const requestedHeaders = req.headers["access-control-request-headers"];
  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader(
    "Access-Control-Allow-Headers",
    typeof requestedHeaders === "string" && requestedHeaders.trim() !== ""
      ? requestedHeaders
      : "Content-Type",
  );
  res.setHeader("Vary", "Origin");
  return true;
};

const server = createServer(async (req, res) => {
  const requestId = randomUUID();
  const requestLogger = logger.child({ requestId, method: req.method, path: req.url ?? "/" });
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const isApiRoute = url.pathname.startsWith("/api/v1/");
  const corsAllowed = isApiRoute ? applyCorsHeaders(req, res) : false;

  if (req.method === "OPTIONS" && isApiRoute) {
    if (!corsAllowed && getOrigin(req)) {
      res.writeHead(403);
      res.end();
      return;
    }

    res.writeHead(204);
    res.end();
    return;
  }

  res.setHeader("Content-Type", "application/json");
  requestLogger.debug("incoming request");

  // GET /api/v1/tools — list enabled tools only
  if (req.method === "GET" && url.pathname === "/api/v1/tools") {
    requestLogger.info("listing tools", { toolCount: enabledTools.length });
    res.end(JSON.stringify(enabledTools.map((t) => ({ name: t.name, description: t.description }))));
    return;
  }

  // GET /api/v1/health
  if (req.method === "GET" && url.pathname === "/api/v1/health") {
    requestLogger.info("health check");
    res.end(JSON.stringify({
      status: "ok",
      tools: enabledTools.length,
      services: {
        gateway: "reachable",
        acra: "available-via-datagov",
        tinyfish: {
          configured: isTinyFishSearchConfigured(),
          mode: "web-discovery-only",
        },
      },
    }));
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/dude/search-suggestions") {
    const query = getQueryValue(url, "q");
    if (query.length < 2) {
      sendJson(res, 200, { query, suggestions: [] });
      return;
    }
    try {
      const startedAt = Date.now();
      const suggestions = await searchAcraEntitySuggestions(query, 6);
      requestLogger.info("search suggestions finished", {
        query,
        suggestions: suggestions.length,
        durationMs: Date.now() - startedAt,
      });
      sendJson(res, 200, { query, suggestions });
    } catch (err) {
      requestLogger.warn("search suggestions failed", {
        query,
        error: err instanceof Error ? err.message : String(err),
      });
      sendJson(res, 200, { query, suggestions: [], warning: "Search suggestions are temporarily unavailable." });
    }
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/dude/web-presence") {
    const query = getQueryValue(url, "query");
    if (query === "") {
      sendJson(res, 400, { error: "query is required" });
      return;
    }
    const startedAt = Date.now();
    const presence = await getWebPresence(query);
    requestLogger.info("web presence finished", {
      query,
      configured: presence.configured,
      results: presence.results.length,
      durationMs: Date.now() - startedAt,
    });
    sendJson(res, 200, presence);
    return;
  }

  // POST /api/v1/<tool-name>
  if (req.method === "POST" && url.pathname.startsWith("/api/v1/")) {
    const toolName = url.pathname.slice(8).replace(/-/g, "_");
    const tool = toolMap.get(toolName) ?? toolMap.get(`sg_${toolName}`);
    if (!tool) {
      requestLogger.warn("tool not found or not enabled", { toolName });
      res.writeHead(404);
      res.end(JSON.stringify({ error: `tool not found or not enabled: ${toolName}` }));
      return;
    }
    try {
      const body = await readBody(req);
      const input = body === "" ? {} : JSON.parse(body);
      const startedAt = Date.now();
      requestLogger.info("invoking tool", {
        tool: tool.name,
        ...(tool.name === "sg_business_dossier" ? summarizeBusinessInput(input) : {}),
      });
      const result = await tool.handler(input);
      const status = result.isError ? 400 : 200;
      requestLogger.info("tool invocation finished", {
        tool: tool.name,
        status,
        isError: result.isError === true,
        durationMs: Date.now() - startedAt,
        ...(tool.name === "sg_business_dossier"
          ? summarizeBusinessDossier(result.structuredContent?.["record"])
          : {}),
      });
      res.writeHead(status);
      res.end(JSON.stringify({
        content: result.content,
        ...(result.structuredContent ? { data: result.structuredContent } : {}),
      }));
    } catch (err) {
      requestLogger.error("tool invocation failed", {
        error: err instanceof Error ? err.message : String(err),
      });
      res.writeHead(500);
      res.end(JSON.stringify({ error: err instanceof Error ? err.message : String(err) }));
    }
    return;
  }

  // fallback
  requestLogger.warn("unknown route");
  res.writeHead(404);
  res.end(JSON.stringify({
    error: "not found",
    hint: "GET /api/v1/tools for available endpoints, POST /api/v1/<tool-name> to call a tool",
  }));
});

server.listen(PORT, () => {
  console.log(`Dude REST gateway listening on http://localhost:${PORT}`);
  console.log(`tools: ${enabledTools.length}/${ALL_TOOL_DEFINITIONS.length} (toolsets: ${[...enabledToolsets].join(",")})`);
  console.log(`try: curl -X POST http://localhost:${PORT}/api/v1/sg_nea_forecast_2hr -d '{"area":"Bedok"}'`);
});
