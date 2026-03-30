import { loadConfig } from "./config/index.js";

const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 } as const;
export type LogLevel = keyof typeof LOG_LEVELS;

export type LogEntry = Readonly<{
  ts: string;
  level: LogLevel;
  module: string;
  msg: string;
}> & Readonly<Record<string, unknown>>;

export type LogSubscriber = (entry: LogEntry) => void;

const MAX_SERIALIZE_DEPTH = 5;
const SENSITIVE_KEY_PATTERN = /(password|secret|token|api[_-]?key|authorization|cookie|session|bearer)/i;

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

const logSubscribers = new Set<LogSubscriber>();

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

const redactValue = (value: unknown): unknown => {
  if (value === null || value === undefined) {
    return value;
  }

  if (typeof value === "bigint") {
    return value.toString();
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (value instanceof Error) {
    return serializeError(value);
  }

  if (Array.isArray(value)) {
    return value.map((item) => redactValue(item));
  }

  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, nestedValue]) => [
        key,
        SENSITIVE_KEY_PATTERN.test(key) ? "[redacted]" : redactValue(nestedValue),
      ]),
    );
  }

  return value;
};

const redactExtra = (extra: Readonly<Record<string, unknown>> | undefined): Readonly<Record<string, unknown>> => {
  const redacted = redactValue(extra ?? {});
  return (redacted !== null && typeof redacted === "object" ? redacted : {}) as Readonly<Record<string, unknown>>;
};

export const subscribeLogEntries = (subscriber: LogSubscriber): (() => void) => {
  logSubscribers.add(subscriber);
  return () => {
    logSubscribers.delete(subscriber);
  };
};

export const createLogger = (module: string): Logger => {
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
      ...redactExtra(inherited),
      ...redactExtra(extra),
    } satisfies LogEntry;

    process.stderr.write(safeJson(entry as LogRecord) + "\n");
    for (const subscriber of logSubscribers) {
      subscriber(entry);
    }
  };

  const createChild = (inheritedExtra: Readonly<Record<string, unknown>>): Logger => ({
    debug: (msg, childExtra) => log("debug", msg, childExtra, inheritedExtra),
    info: (msg, childExtra) => log("info", msg, childExtra, inheritedExtra),
    warn: (msg, childExtra) => log("warn", msg, childExtra, inheritedExtra),
    error: (msg, childExtra) => log("error", msg, childExtra, inheritedExtra),
    child: (nestedExtra) => createChild({ ...inheritedExtra, ...nestedExtra }),
  });

  return {
    debug: (msg, extra) => log("debug", msg, extra),
    info: (msg, extra) => log("info", msg, extra),
    warn: (msg, extra) => log("warn", msg, extra),
    error: (msg, extra) => log("error", msg, extra),
    child: (extra) => createChild(extra),
  };
};
