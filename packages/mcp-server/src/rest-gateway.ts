#!/usr/bin/env node
// REST gateway: exposes sg_* tools as HTTP POST endpoints
// usage: node packages/mcp-server/dist/rest-gateway.js
// env: PORT (default 3000), SG_APIS_TOOLSETS, SG_APIS_TOOL_PROFILE (default public profile)
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { randomUUID } from "node:crypto";
import { createLogger } from "@dude/shared";
import { searchAcraEntitySuggestions } from "./apis/acra/client.js";
import { getPeopleDiscovery, getWebPresence } from "./apis/tinyfish/client.js";
import { buildBulkDossierResponse } from "./dude/bulk-dossiers.js";
import { generateAnalystMemo, type AnalystMemoDossier } from "./dude/analyst-memo.js";
import {
  getGatewayMetricsSnapshot,
  recordGatewayRequest,
  recordUpstreamFailures,
} from "./gateway/metrics.js";
import { buildDisabledDebugLogSnapshot, initDebugLogStore } from "./gateway/debug-log-store.js";
import { getGatewayHealthPayload } from "./gateway/readiness.js";
import {
  buildRateLimitResponse,
  checkTrafficLimit,
  getClientId,
  getTrafficPolicy,
} from "./gateway/traffic-control.js";
import { ALL_TOOL_DEFINITIONS } from "./tools/tool-set.js";
import { handleBusinessDossier } from "./tools/brief-tools.js";
import { isToolEnabled } from "./tools/tool-metadata.js";
import {
  WorkspaceApiAccessError,
  assertWorkspaceApiAccess,
  parseWorkspaceApiSession,
  resolveWorkspaceApiAuthPolicy,
  type WorkspacePermission,
} from "./workspace/access-control.js";
const PORT = Number(process.env["PORT"] ?? 3000);
const DEFAULT_DEV_WEB_ORIGIN_ALLOWLIST = "http://localhost:5173,http://127.0.0.1:5173";
const gatewayStartedAt = new Date();
const debugLogStore = initDebugLogStore();
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
const configuredCorsOrigins = process.env["DUDE_WEB_ORIGIN_ALLOWLIST"] ?? "";
const defaultCorsOrigins = process.env["NODE_ENV"] === "production"
  ? ""
  : DEFAULT_DEV_WEB_ORIGIN_ALLOWLIST;
const allowedCorsOrigins = new Set(
  `${defaultCorsOrigins},${configuredCorsOrigins}`
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
);
const workspaceAuthPolicy = resolveWorkspaceApiAuthPolicy();

logger.info("gateway started", {
  toolsets: [...enabledToolsets],
  tools: enabledTools.length,
  total: ALL_TOOL_DEFINITIONS.length,
  debugLogsEnabled: debugLogStore.enabled,
  workspaceAuth: workspaceAuthPolicy.details,
  ...(debugLogStore.logPath === undefined ? {} : { debugLogPath: debugLogStore.logPath }),
});

const MAX_SEARCH_QUERY_LENGTH = 96;
const MAX_WEB_PRESENCE_QUERY_LENGTH = 160;
const MAX_PEOPLE_DISCOVERY_ENTITY_LENGTH = 128;
const MAX_MEMO_IDENTIFIER_LENGTH = 128;
const UEN_PATTERN = /^(?:\d{8,9}[a-z]|[a-z]\d{2}[a-z]{2}\d{4}[a-z])$/i;
const WORKSPACE_AUTH_REQUIRED = workspaceAuthPolicy.authRequired;
const DEBUG_LOGS_PRODUCTION_DISABLED_MESSAGE =
  "Debug log access is disabled in production unless DUDE_WORKSPACE_AUTH_REQUIRED=true and the request has admin/debug permissions.";

class RequestBodyTooLargeError extends Error {
  readonly statusCode = 413;

  constructor(readonly maxBytes: number) {
    super(`Request body exceeds ${maxBytes} bytes.`);
    this.name = "RequestBodyTooLargeError";
  }
}

class BadRequestError extends Error {
  readonly statusCode = 400;

  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "BadRequestError";
  }
}

const requireWorkspaceAccess = (
  req: IncomingMessage,
  permission: WorkspacePermission,
): ReturnType<typeof parseWorkspaceApiSession> => {
  const session = parseWorkspaceApiSession(req.headers, { authRequired: WORKSPACE_AUTH_REQUIRED });
  assertWorkspaceApiAccess(session, permission);
  return session;
};

const sendWorkspaceAccessError = (res: ServerResponse, error: WorkspaceApiAccessError): void => {
  sendJson(res, error.statusCode, {
    error: {
      code: error.code,
      message: error.message,
    },
  });
};

const readBody = (req: IncomingMessage, maxBytes: number): Promise<string> =>
  new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let totalBytes = 0;
    let rejected = false;
    req.on("data", (c: Buffer) => {
      if (rejected) {
        return;
      }
      totalBytes += c.byteLength;
      if (totalBytes > maxBytes) {
        rejected = true;
        reject(new RequestBodyTooLargeError(maxBytes));
        req.resume();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });

const sendJson = (res: ServerResponse, status: number, body: unknown): void => {
  res.writeHead(status);
  res.end(JSON.stringify(body));
};

const getQueryValue = (url: URL, key: string): string => url.searchParams.get(key)?.trim() ?? "";

const buildLimitMessage = (
  name: string,
  limit: number,
): { readonly error: { readonly code: string; readonly message: string } } => ({
  error: {
    code: "INPUT_TOO_LARGE",
    message: `${name} must be ${limit} characters or fewer.`,
  },
});

const summarizeQueryInput = (value: string): Record<string, unknown> => ({
  queryLength: value.length,
  queryLooksLikeUen: /^(?:\d{8,9}[a-z]|[a-z]\d{2}[a-z]{2}\d{4}[a-z])$/i.test(value),
});

const summarizeBusinessInput = (input: unknown): Record<string, unknown> => {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    return {};
  }
  const record = input as Record<string, unknown>;
  const modules = Array.isArray(record["modules"])
    ? record["modules"].filter((module): module is string => typeof module === "string")
    : [];
  const entityName = typeof record["entityName"] === "string" ? record["entityName"].trim() : "";
  return {
    hasUen: typeof record["uen"] === "string" && record["uen"].trim() !== "",
    ...(typeof record["uen"] === "string" ? { uen: record["uen"].trim().toUpperCase() } : {}),
    ...(entityName === "" ? {} : { entityNameLength: entityName.length }),
    ...(modules.length === 0 ? {} : { modules }),
  };
};

const summarizeMemoInput = (input: unknown): Record<string, unknown> => {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    return {};
  }
  const record = input as Record<string, unknown>;
  const identifier = typeof record["identifier"] === "string" ? record["identifier"].trim() : "";
  const dossier = record["dossier"];
  const webPresence = record["webPresence"];
  return {
    hasDossier: dossier !== null && typeof dossier === "object" && !Array.isArray(dossier),
    ...(identifier === "" ? {} : {
      identifierLength: identifier.length,
      identifierLooksLikeUen: UEN_PATTERN.test(identifier),
    }),
    hasWebPresenceLimits: webPresence !== null
      && typeof webPresence === "object"
      && !Array.isArray(webPresence)
      && Array.isArray((webPresence as Record<string, unknown>)["limits"]),
  };
};

const summarizeBulkInput = (input: unknown): Record<string, unknown> => {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    return {};
  }
  const record = input as Record<string, unknown>;
  const items = record["items"];
  return {
    requestedCount: Array.isArray(items) ? items.length : 0,
  };
};

const summarizeBusinessDossier = (record: unknown): {
  readonly matchedModules: readonly string[];
  readonly unmatchedModules: readonly string[];
  readonly gapCodes: readonly string[];
  readonly upstreamFailures: readonly string[];
} => {
  if (record === null || typeof record !== "object" || Array.isArray(record)) {
    return {
      matchedModules: [],
      unmatchedModules: [],
      gapCodes: [],
      upstreamFailures: [],
    };
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
  const gapCodes = gaps
    .map((gap) => gap.code)
    .filter((code): code is string => typeof code === "string");
  return {
    matchedModules: dossier.records?.resolution?.matchedModules ?? [],
    unmatchedModules: dossier.records?.resolution?.unmatchedModules ?? [],
    gapCodes,
    upstreamFailures: gapCodes.filter((code) => code.includes("UNAVAILABLE")),
  };
};

const getOrigin = (req: IncomingMessage): string | undefined => {
  const origin = req.headers.origin;
  return typeof origin === "string" ? origin : undefined;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const isDossier = (value: unknown): value is AnalystMemoDossier =>
  isRecord(value)
  && typeof value["title"] === "string"
  && Array.isArray(value["summary"])
  && Array.isArray(value["evidence"])
  && isRecord(value["records"])
  && Array.isArray(value["gaps"])
  && Array.isArray(value["provenance"])
  && Array.isArray(value["freshness"])
  && Array.isArray(value["limits"]);

const buildBusinessDossierInputFromIdentifier = (identifier: string): { readonly uen: string } | { readonly entityName: string } =>
  UEN_PATTERN.test(identifier)
    ? { uen: identifier.toUpperCase() }
    : { entityName: identifier };

const resolveMemoDossier = async (input: Record<string, unknown>): Promise<AnalystMemoDossier> => {
  if (isDossier(input["dossier"])) {
    return input["dossier"];
  }

  const identifier = typeof input["identifier"] === "string" ? input["identifier"].trim() : "";
  if (identifier === "") {
    throw new BadRequestError("MEMO_DOSSIER_REQUIRED", "Provide a dossier envelope or an identifier to resolve one.");
  }
  if (identifier.length > MAX_MEMO_IDENTIFIER_LENGTH) {
    throw new BadRequestError("INPUT_TOO_LARGE", `Memo identifier must be ${MAX_MEMO_IDENTIFIER_LENGTH} characters or fewer.`);
  }

  const result = await handleBusinessDossier(buildBusinessDossierInputFromIdentifier(identifier));
  const record = result.structuredContent?.["record"];
  if (!isDossier(record)) {
    throw new BadRequestError("MEMO_DOSSIER_RESOLUTION_FAILED", "Unable to resolve a business dossier for analyst memo generation.");
  }
  return record;
};

const sanitizeWebPresenceForMemo = (
  value: unknown,
): { readonly configured: boolean; readonly limits: readonly string[] } | undefined => {
  if (!isRecord(value)) {
    return undefined;
  }
  const configured = value["configured"];
  const limits = value["limits"];
  return {
    configured: configured === true,
    limits: Array.isArray(limits)
      ? limits.filter((item): item is string => typeof item === "string" && item.trim() !== "").map((item) => item.trim())
      : [],
  };
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
  const requestStartedAt = Date.now();
  const requestId = randomUUID();
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const method = req.method ?? "UNKNOWN";
  const route = url.pathname;
  const requestLogger = logger.child({ requestId, method, route });
  let safeInputSummary: Record<string, unknown> = {};
  const isApiRoute = url.pathname.startsWith("/api/v1/");
  const corsAllowed = isApiRoute ? applyCorsHeaders(req, res) : false;

  res.on("finish", () => {
    const durationMs = Date.now() - requestStartedAt;
    recordGatewayRequest({
      method,
      route,
      status: res.statusCode,
      durationMs,
    });
    requestLogger.info("request finished", {
      status: res.statusCode,
      durationMs,
      ...(Object.keys(safeInputSummary).length === 0 ? {} : { input: safeInputSummary }),
    });
  });

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

  const trafficPolicy = getTrafficPolicy(method, route);
  const trafficLimit = checkTrafficLimit({
    clientId: getClientId(req),
    policy: trafficPolicy,
  });
  res.setHeader("X-RateLimit-Limit", String(trafficPolicy.maxRequests));
  res.setHeader("X-RateLimit-Remaining", String(trafficLimit.remaining));
  res.setHeader("X-RateLimit-Reset", String(Math.ceil(trafficLimit.resetAt / 1000)));
  if (!trafficLimit.allowed) {
    res.setHeader("Retry-After", String(trafficLimit.retryAfterSeconds));
    sendJson(res, 429, buildRateLimitResponse(trafficPolicy, trafficLimit));
    return;
  }

  // GET /api/v1/tools — list enabled tools only
  if (req.method === "GET" && url.pathname === "/api/v1/tools") {
    requestLogger.info("listing tools", { toolCount: enabledTools.length });
    res.end(JSON.stringify(enabledTools.map((t) => ({ name: t.name, description: t.description }))));
    return;
  }

  // GET /api/v1/health
  if (req.method === "GET" && url.pathname === "/api/v1/health") {
    requestLogger.info("health check");
    const health = await getGatewayHealthPayload({
      gateway: {
        status: workspaceAuthPolicy.productionFailClosed ? "failing" : "ready",
        message: workspaceAuthPolicy.message,
        observedAt: new Date().toISOString(),
        details: workspaceAuthPolicy.details,
      },
      toolCount: enabledTools.length,
      startedAt: gatewayStartedAt,
    });
    res.end(JSON.stringify(health));
    return;
  }

  // GET /api/v1/metrics
  if (req.method === "GET" && url.pathname === "/api/v1/metrics") {
    requestLogger.info("metrics snapshot");
    res.end(JSON.stringify(getGatewayMetricsSnapshot({ startedAt: gatewayStartedAt })));
    return;
  }

  // GET /api/v1/debug/logs
  if (req.method === "GET" && url.pathname === "/api/v1/debug/logs") {
    try {
      requireWorkspaceAccess(req, "debug:read");
    } catch (err) {
      if (err instanceof WorkspaceApiAccessError) {
        sendWorkspaceAccessError(res, err);
        return;
      }
      throw err;
    }
    const limitParam = Number(url.searchParams.get("limit") ?? "");
    const level = url.searchParams.get("level")?.trim().toLowerCase();
    const rawSnapshot = debugLogStore.getSnapshot(Number.isFinite(limitParam) && limitParam > 0 ? limitParam : undefined);
    const snapshot = workspaceAuthPolicy.production && !workspaceAuthPolicy.explicitWorkspaceAuth
      ? buildDisabledDebugLogSnapshot(DEBUG_LOGS_PRODUCTION_DISABLED_MESSAGE, rawSnapshot)
      : rawSnapshot;
    const entries = level === undefined || level === ""
      ? snapshot.entries
      : snapshot.entries.filter((entry) => entry.level === level);
    requestLogger.info("debug log snapshot", {
      enabled: snapshot.enabled,
      returnedEntries: entries.length,
      totalEntries: snapshot.totalEntries,
    });
    sendJson(res, 200, {
      ...snapshot,
      entries,
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/dude/search-suggestions") {
    try {
      requireWorkspaceAccess(req, "search:run");
    } catch (err) {
      if (err instanceof WorkspaceApiAccessError) {
        sendWorkspaceAccessError(res, err);
        return;
      }
      throw err;
    }
    const query = getQueryValue(url, "q");
    safeInputSummary = summarizeQueryInput(query);
    if (query.length > MAX_SEARCH_QUERY_LENGTH) {
      sendJson(res, 400, buildLimitMessage("Search query", MAX_SEARCH_QUERY_LENGTH));
      return;
    }
    if (query.length < 2) {
      sendJson(res, 200, { query, suggestions: [] });
      return;
    }
    try {
      const startedAt = Date.now();
      const suggestions = await searchAcraEntitySuggestions(query, 6);
      requestLogger.info("search suggestions finished", {
        ...summarizeQueryInput(query),
        suggestions: suggestions.length,
        durationMs: Date.now() - startedAt,
      });
      sendJson(res, 200, { query, suggestions });
    } catch (err) {
      requestLogger.warn("search suggestions failed", {
        ...summarizeQueryInput(query),
        error: err instanceof Error ? err.message : String(err),
      });
      sendJson(res, 200, { query, suggestions: [], warning: "Search suggestions are temporarily unavailable." });
    }
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/dude/web-presence") {
    try {
      requireWorkspaceAccess(req, "dossier:read");
    } catch (err) {
      if (err instanceof WorkspaceApiAccessError) {
        sendWorkspaceAccessError(res, err);
        return;
      }
      throw err;
    }
    const query = getQueryValue(url, "query");
    safeInputSummary = summarizeQueryInput(query);
    if (query.length > MAX_WEB_PRESENCE_QUERY_LENGTH) {
      sendJson(res, 400, buildLimitMessage("Web discovery query", MAX_WEB_PRESENCE_QUERY_LENGTH));
      return;
    }
    if (query === "") {
      sendJson(res, 400, { error: "query is required" });
      return;
    }
    const startedAt = Date.now();
    const presence = await getWebPresence(query);
    requestLogger.info("web presence finished", {
      ...summarizeQueryInput(query),
      configured: presence.configured,
      results: presence.results.length,
      durationMs: Date.now() - startedAt,
    });
    sendJson(res, 200, presence);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/v1/dude/people-discovery") {
    try {
      requireWorkspaceAccess(req, "dossier:read");
    } catch (err) {
      if (err instanceof WorkspaceApiAccessError) {
        sendWorkspaceAccessError(res, err);
        return;
      }
      throw err;
    }
    const entityName = getQueryValue(url, "entityName");
    const uen = getQueryValue(url, "uen");
    safeInputSummary = summarizeQueryInput(entityName);
    if (entityName.length > MAX_PEOPLE_DISCOVERY_ENTITY_LENGTH) {
      sendJson(res, 400, buildLimitMessage("People discovery entity name", MAX_PEOPLE_DISCOVERY_ENTITY_LENGTH));
      return;
    }
    if (entityName === "") {
      sendJson(res, 400, { error: "entityName is required" });
      return;
    }
    const startedAt = Date.now();
    const discovery = await getPeopleDiscovery({
      entityName,
      ...(uen === "" ? {} : { uen }),
    });
    requestLogger.info("people discovery finished", {
      ...summarizeQueryInput(entityName),
      configured: discovery.configured,
      results: discovery.results.length,
      durationMs: Date.now() - startedAt,
    });
    sendJson(res, 200, discovery);
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/v1/dude/memo") {
    try {
      requireWorkspaceAccess(req, "memo:generate");
      const body = await readBody(req, trafficPolicy.maxBodyBytes);
      const input = body === "" ? {} : JSON.parse(body);
      if (!isRecord(input)) {
        throw new BadRequestError("INVALID_MEMO_INPUT", "Memo request body must be a JSON object.");
      }
      safeInputSummary = summarizeMemoInput(input);
      const startedAt = Date.now();
      const dossier = await resolveMemoDossier(input);
      const webPresence = sanitizeWebPresenceForMemo(input["webPresence"]);
      const memo = await generateAnalystMemo({
        dossier,
        ...(webPresence === undefined ? {} : { webPresence }),
      });
      requestLogger.info("analyst memo finished", {
        ...safeInputSummary,
        status: memo.status,
        configured: memo.configured,
        provider: memo.provider,
        durationMs: Date.now() - startedAt,
      });
      sendJson(res, 200, memo);
    } catch (err) {
      if (err instanceof WorkspaceApiAccessError) {
        requestLogger.warn("memo workspace access denied", { code: err.code });
        sendWorkspaceAccessError(res, err);
        return;
      }
      if (err instanceof RequestBodyTooLargeError) {
        requestLogger.warn("memo request body too large", { maxBytes: err.maxBytes });
        sendJson(res, err.statusCode, {
          error: {
            code: "REQUEST_BODY_TOO_LARGE",
            message: `Request body must be ${err.maxBytes} bytes or smaller.`,
          },
        });
        return;
      }
      if (err instanceof BadRequestError) {
        requestLogger.warn("invalid memo request", { code: err.code });
        sendJson(res, err.statusCode, {
          error: {
            code: err.code,
            message: err.message,
          },
        });
        return;
      }
      if (err instanceof SyntaxError) {
        requestLogger.warn("invalid memo json body");
        sendJson(res, 400, {
          error: {
            code: "INVALID_JSON",
            message: "Request body must be valid JSON.",
          },
        });
        return;
      }
      requestLogger.error("analyst memo failed", {
        error: err instanceof Error ? err.message : String(err),
      });
      sendJson(res, 500, {
        error: {
          code: "MEMO_GENERATION_FAILED",
          message: "Analyst memo generation failed.",
        },
      });
    }
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/v1/dude/bulk-dossiers") {
    try {
      requireWorkspaceAccess(req, "bulk:run");
      const body = await readBody(req, trafficPolicy.maxBodyBytes);
      const input = body === "" ? {} : JSON.parse(body);
      safeInputSummary = summarizeBulkInput(input);
      const startedAt = Date.now();
      const response = await buildBulkDossierResponse(input, handleBusinessDossier);
      requestLogger.info("bulk dossiers finished", {
        ...safeInputSummary,
        executedCount: response.executedCount,
        parseErrors: response.parseErrors.length,
        durationMs: Date.now() - startedAt,
      });
      sendJson(res, 200, response);
    } catch (err) {
      if (err instanceof WorkspaceApiAccessError) {
        requestLogger.warn("bulk workspace access denied", { code: err.code });
        sendWorkspaceAccessError(res, err);
        return;
      }
      if (err instanceof RequestBodyTooLargeError) {
        requestLogger.warn("bulk request body too large", { maxBytes: err.maxBytes });
        sendJson(res, err.statusCode, {
          error: {
            code: "REQUEST_BODY_TOO_LARGE",
            message: `Request body must be ${err.maxBytes} bytes or smaller.`,
          },
        });
        return;
      }
      if (err instanceof SyntaxError) {
        requestLogger.warn("invalid bulk json body");
        sendJson(res, 400, {
          error: {
            code: "INVALID_JSON",
            message: "Request body must be valid JSON.",
          },
        });
        return;
      }
      requestLogger.error("bulk dossiers failed", {
        error: err instanceof Error ? err.message : String(err),
      });
      sendJson(res, 500, {
        error: {
          code: "BULK_DOSSIERS_FAILED",
          message: "Bulk dossier execution failed.",
        },
      });
    }
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
      requireWorkspaceAccess(req, tool.name === "sg_business_dossier" ? "search:run" : "dossier:read");
      const body = await readBody(req, trafficPolicy.maxBodyBytes);
      const input = body === "" ? {} : JSON.parse(body);
      const startedAt = Date.now();
      const inputSummary = tool.name === "sg_business_dossier" ? summarizeBusinessInput(input) : {};
      safeInputSummary = { tool: tool.name, ...inputSummary };
      requestLogger.info("invoking tool", {
        tool: tool.name,
        ...inputSummary,
      });
      const result = await tool.handler(input);
      const status = result.isError ? 400 : 200;
      const dossierSummary = tool.name === "sg_business_dossier"
        ? summarizeBusinessDossier(result.structuredContent?.["record"])
        : undefined;
      if (dossierSummary !== undefined) {
        recordUpstreamFailures(tool.name, dossierSummary.upstreamFailures);
      }
      requestLogger.info("tool invocation finished", {
        tool: tool.name,
        status,
        isError: result.isError === true,
        durationMs: Date.now() - startedAt,
        ...(dossierSummary ?? {}),
      });
      res.writeHead(status);
      res.end(JSON.stringify({
        content: result.content,
        ...(result.structuredContent ? { data: result.structuredContent } : {}),
      }));
    } catch (err) {
      if (err instanceof WorkspaceApiAccessError) {
        requestLogger.warn("tool workspace access denied", { code: err.code });
        sendWorkspaceAccessError(res, err);
        return;
      }
      if (err instanceof RequestBodyTooLargeError) {
        requestLogger.warn("request body too large", { maxBytes: err.maxBytes });
        sendJson(res, err.statusCode, {
          error: {
            code: "REQUEST_BODY_TOO_LARGE",
            message: `Request body must be ${err.maxBytes} bytes or smaller.`,
          },
        });
        return;
      }
      if (err instanceof SyntaxError) {
        requestLogger.warn("invalid json body");
        sendJson(res, 400, {
          error: {
            code: "INVALID_JSON",
            message: "Request body must be valid JSON.",
          },
        });
        return;
      }
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
