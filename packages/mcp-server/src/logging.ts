import { subscribeLogEntries } from "@swee-sg/shared";
import type { LogEntry, LogLevel } from "@swee-sg/shared";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { SetLevelRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const LEVEL_SEVERITY: Readonly<Record<LogLevel, number>> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const STDIO_SESSION_KEY = "stdio";

const resolveSessionKey = (
  sessionId: string | undefined,
  requestHeaders: Record<string, string | string[] | undefined> | undefined,
): string => {
  const headerValue = requestHeaders?.["mcp-session-id"];
  const normalizedHeader = Array.isArray(headerValue) ? headerValue[0] : headerValue;
  return sessionId ?? normalizedHeader ?? STDIO_SESSION_KEY;
};

const shouldSendLogEntry = (entry: LogEntry, level: LogLevel): boolean => {
  return LEVEL_SEVERITY[entry.level] >= LEVEL_SEVERITY[level];
};

const toMcpLogLevel = (level: LogLevel): "debug" | "info" | "warning" | "error" => {
  if (level === "warn") {
    return "warning";
  }
  return level;
};

export type LoggingBridge = {
  readonly close: () => void;
};

export const attachLoggingBridge = (server: McpServer): LoggingBridge => {
  const sessionLevels = new Map<string, LogLevel>();

  server.server.setRequestHandler(SetLevelRequestSchema, async (request, extra) => {
    const sessionKey = resolveSessionKey(extra.sessionId, extra.requestInfo?.headers);
    sessionLevels.set(sessionKey, request.params.level as LogLevel);
    return {};
  });

  const unsubscribe = subscribeLogEntries((entry) => {
    for (const [sessionKey, level] of sessionLevels) {
      if (!shouldSendLogEntry(entry, level)) {
        continue;
      }

      void server.sendLoggingMessage({
        level: toMcpLogLevel(entry.level),
        logger: entry.module,
        data: {
          message: entry.msg,
          ...entry,
        },
      }, sessionKey === STDIO_SESSION_KEY ? undefined : sessionKey).catch(() => undefined);
    }
  });

  return {
    close: unsubscribe,
  };
};
