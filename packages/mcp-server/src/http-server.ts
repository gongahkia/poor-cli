import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import {
  createServer,
  type IncomingMessage,
  type Server as HttpServer,
  type ServerResponse,
} from "node:http";
import type { AddressInfo } from "node:net";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import type { Logger, LogLevel } from "@dude/shared";
import { HttpAuthController, type AuthorizedSession } from "./http-auth.js";
import { createServerInstance, type ServerInstance } from "./server-factory.js";

type StartHttpServerOptions = {
  readonly host: string;
  readonly port: number;
  readonly auth: HttpAuthController;
  readonly useBoundResourceServerUrl?: boolean;
  readonly logger: Logger;
};

type SessionState = AuthorizedSession & {
  readonly instance: ServerInstance;
  readonly transport: StreamableHTTPServerTransport;
};

type StartedHttpServer = {
  readonly server: HttpServer;
  readonly close: () => Promise<void>;
};

const LOCAL_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);
const ICON_SVG = readFileSync(new URL("../assets/icon.svg", import.meta.url), "utf8");

const isInitializeRequest = (body: unknown): boolean => {
  return typeof body === "object"
    && body !== null
    && !Array.isArray(body)
    && "method" in body
    && body.method === "initialize";
};

const toHeaderValue = (value: string | string[] | undefined): string | undefined => {
  return Array.isArray(value) ? value[0] : value;
};

const readBody = (req: IncomingMessage): Promise<string> =>
  new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });

const parseBody = async (req: IncomingMessage): Promise<unknown> => {
  if (req.method !== "POST" && req.method !== "DELETE") {
    return undefined;
  }

  const rawBody = await readBody(req);
  if (rawBody.trim() === "") {
    return undefined;
  }
  return JSON.parse(rawBody);
};

const writeJson = (
  res: ServerResponse,
  statusCode: number,
  payload: Record<string, unknown>,
  headers?: Readonly<Record<string, string>>,
): void => {
  res.writeHead(statusCode, {
    "Content-Type": "application/json",
    ...(headers ?? {}),
  });
  res.end(JSON.stringify(payload));
};

const writeText = (
  res: ServerResponse,
  statusCode: number,
  payload: string,
  contentType: string,
): void => {
  res.writeHead(statusCode, { "Content-Type": contentType });
  res.end(payload);
};

const resolveLogLevel = (statusCode: number): LogLevel => {
  if (statusCode >= 500) {
    return "error";
  }
  if (statusCode >= 400) {
    return "warn";
  }
  return "info";
};

export const isLocalHost = (host: string): boolean => {
  return LOCAL_HOSTS.has(host);
};

const normalizeBoundHost = (host: string): string => {
  if (host === "::") {
    return "127.0.0.1";
  }
  return host;
};

export const startHttpServer = async (options: StartHttpServerOptions): Promise<StartedHttpServer> => {
  const sessions = new Map<string, SessionState>();

  const cleanupSession = async (sessionId: string): Promise<void> => {
    const session = sessions.get(sessionId);
    if (session === undefined) {
      return;
    }
    sessions.delete(sessionId);
    await session.instance.close();
  };

  const server = createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", options.auth.resourceServerUrl);
    const log = (statusCode: number, msg: string, extra?: Readonly<Record<string, unknown>>) => {
      const level = resolveLogLevel(statusCode);
      options.logger[level](msg, {
        method: req.method ?? "UNKNOWN",
        path: url.pathname,
        ...extra,
      });
    };

    const hostHeaderFailure = options.auth.validateLocalHostHeader(req);
    if (hostHeaderFailure !== null) {
      log(hostHeaderFailure.statusCode, "Rejected request with invalid host header");
      writeJson(res, hostHeaderFailure.statusCode, { ...hostHeaderFailure.payload }, hostHeaderFailure.headers);
      return;
    }

    if (url.pathname === "/healthz" && req.method === "GET") {
      writeJson(res, 200, { status: "ok", sessions: sessions.size });
      return;
    }

    if (url.pathname === "/icon.svg" && req.method === "GET") {
      writeText(res, 200, ICON_SVG, "image/svg+xml");
      return;
    }

    if (url.pathname === options.auth.protectedResourceMetadataPath && req.method === "GET") {
      writeJson(res, 200, { ...options.auth.protectedResourceMetadata });
      return;
    }

    if (url.pathname !== "/mcp") {
      writeJson(res, 404, { error: "not_found", hint: "Use /mcp for the MCP Streamable HTTP endpoint." });
      return;
    }

    let parsedBody: unknown;
    try {
      parsedBody = await parseBody(req);
    } catch (error) {
      log(400, "Rejected invalid JSON body", {
        error: error instanceof Error ? error.message : String(error),
      });
      writeJson(res, 400, { error: "invalid_json" });
      return;
    }

    const sessionId = toHeaderValue(req.headers["mcp-session-id"]);

    try {
      if (req.method === "POST" && sessionId === undefined && isInitializeRequest(parsedBody)) {
        const sessionAuth = await options.auth.resolveInitializeSession(req);
        if ("statusCode" in sessionAuth) {
          log(sessionAuth.statusCode, "Rejected unauthorized MCP HTTP initialization", {
            reason: sessionAuth.reason,
          });
          writeJson(res, sessionAuth.statusCode, { ...sessionAuth.payload }, sessionAuth.headers);
          return;
        }

        const instance = createServerInstance({
          enabledToolsets: sessionAuth.enabledToolsets,
          baseUrl: options.auth.resourceServerUrl,
        });
        const transport = new StreamableHTTPServerTransport({
          sessionIdGenerator: () => randomUUID(),
        });

        transport.onclose = () => {
          if (transport.sessionId !== undefined) {
            void cleanupSession(transport.sessionId);
          }
        };

        await instance.server.connect(transport as Parameters<typeof instance.server.connect>[0]);
        await transport.handleRequest(req, res, parsedBody);

        if (transport.sessionId !== undefined) {
          sessions.set(transport.sessionId, {
            ...sessionAuth,
            instance,
            transport,
          });
        }

        log(200, "Initialized MCP HTTP session", {
          sessionId: transport.sessionId,
          access: sessionAuth.access,
          toolsets: Array.from(sessionAuth.enabledToolsets),
        });
        return;
      }

      if (sessionId === undefined) {
        log(400, "Rejected MCP HTTP request without session id");
        writeJson(res, 400, { error: "missing_session_id" });
        return;
      }

      const session = sessions.get(sessionId);
      if (session === undefined) {
        log(404, "Rejected request for unknown MCP session", { sessionId });
        writeJson(res, 404, { error: "unknown_session" });
        return;
      }

      const sessionAuth = await options.auth.authorizeSessionRequest(req, session);
      if (sessionAuth !== true) {
        log(sessionAuth.statusCode, "Rejected unauthorized MCP HTTP session request", {
          sessionId,
          reason: sessionAuth.reason,
        });
        writeJson(res, sessionAuth.statusCode, { ...sessionAuth.payload }, sessionAuth.headers);
        return;
      }

      await session.transport.handleRequest(req, res, parsedBody);
    } catch (error) {
      log(500, "MCP HTTP request failed", {
        error: error instanceof Error ? error.message : String(error),
        sessionId,
      });
      if (!res.headersSent) {
        writeJson(res, 500, {
          error: "internal_error",
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }
  });

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(options.port, options.host, () => {
      server.off("error", reject);
      resolve();
    });
  });

  const address = server.address() as AddressInfo;
  if (options.useBoundResourceServerUrl === true) {
    const resourceServerUrl = new URL(`http://${normalizeBoundHost(options.host)}:${address.port}/mcp`);
    options.auth.setResourceServerUrl(resourceServerUrl);
  }

  return {
    server,
    close: async () => {
      for (const sessionId of [...sessions.keys()]) {
        await cleanupSession(sessionId);
      }

      await new Promise<void>((resolve, reject) => {
        server.close((error) => {
          if (error) {
            reject(error);
            return;
          }
          resolve();
        });
      });
    },
  };
};
