import { loadConfig } from "./config/index.js";

const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 } as const;
type LogLevel = keyof typeof LOG_LEVELS;
const MAX_SERIALIZE_DEPTH = 5;
const SENSITIVE_KEY_PATTERN = /(password|secret|token|api[_-]?key|authorization|cookie|session)/i;

type LogValue = unknown;
type LogRecord = Record<string, LogValue>;

type SanitizeContext = {
  readonly depth: number;
  readonly seen: WeakSet<object>;
};

const serializeError = (error: Error): LogRecord => ({
  name: error.name,
  message: error.message,
  ...(error.stack === undefined ? {} : { stack: error.stack }),
});

const sanitizeValue = (value: LogValue, context: SanitizeContext): LogValue => {
  if (value === null || value === undefined) {
    return value;
  }

  if (typeof value === "bigint") {
    return value.toString();
  }

  if (typeof value !== "object") {
    return value;
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (value instanceof Error) {
    return serializeError(value);
  }

  if (context.depth >= MAX_SERIALIZE_DEPTH) {
    return "[max_depth_exceeded]";
  }

  if (context.seen.has(value)) {
    return "[circular_reference]";
  }

  context.seen.add(value);
  const nextContext: SanitizeContext = {
    depth: context.depth + 1,
    seen: context.seen,
  };

  if (Array.isArray(value)) {
    return value.map((item) => sanitizeValue(item, nextContext));
  }

  const output: LogRecord = {};
  for (const [key, nested] of Object.entries(value)) {
    output[key] = SENSITIVE_KEY_PATTERN.test(key)
      ? "[redacted]"
      : sanitizeValue(nested, nextContext);
  }
  return output;
};

const safeJson = (entry: LogRecord): string => {
  try {
    return JSON.stringify(sanitizeValue(entry, { depth: 0, seen: new WeakSet<object>() }));
  } catch (error) {
    return JSON.stringify({
      ts: new Date().toISOString(),
      level: "error",
      module: "logger",
      msg: "Failed to serialize log entry",
      error: error instanceof Error ? serializeError(error) : String(error),
    });
  }
};

export type Logger = {
  readonly debug: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly info: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly warn: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly error: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly child: (extra: Readonly<Record<string, unknown>>) => Logger;
};

const getConfiguredLevel = (): LogLevel => {
  try {
    const configured = loadConfig().logLevel;
    if (configured in LOG_LEVELS) {
      return configured as LogLevel;
    }
  } catch {
    return "info";
  }
  return "info";
};

export const createLogger = (module: string): Logger => {
  const baseExtra: LogRecord = {};

  const log = (
    level: LogLevel,
    msg: string,
    extra?: Readonly<Record<string, unknown>>,
    inherited?: Readonly<Record<string, unknown>>,
  ): void => {
    const minLevel = LOG_LEVELS[getConfiguredLevel()];
    if (LOG_LEVELS[level] < minLevel) return;
    const entry = {
      ts: new Date().toISOString(),
      level,
      module,
      pid: process.pid,
      msg,
      ...baseExtra,
      ...(inherited ?? {}),
      ...(extra ?? {}),
    };
    process.stderr.write(safeJson(entry) + "\n");
  };

  return {
    debug: (msg, extra) => log("debug", msg, extra),
    info: (msg, extra) => log("info", msg, extra),
    warn: (msg, extra) => log("warn", msg, extra),
    error: (msg, extra) => log("error", msg, extra),
    child: (extra) => ({
      debug: (msg, childExtra) => log("debug", msg, childExtra, extra),
      info: (msg, childExtra) => log("info", msg, childExtra, extra),
      warn: (msg, childExtra) => log("warn", msg, childExtra, extra),
      error: (msg, childExtra) => log("error", msg, childExtra, extra),
      child: (nestedExtra) => createLogger(module).child({ ...extra, ...nestedExtra }),
    }),
  };
};
