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

export type Logger = {
  readonly debug: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly info: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly warn: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly error: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
};

const logSubscribers = new Set<LogSubscriber>();
const REDACTED = "[REDACTED]";
const SECRET_KEY_PATTERN = /(token|secret|password|authorization|bearer|apikey|api_key)/i;

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
  if (Array.isArray(value)) {
    return value.map((item) => redactValue(item));
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, nestedValue]) => [
        key,
        SECRET_KEY_PATTERN.test(key) ? REDACTED : redactValue(nestedValue),
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
  const log = (level: LogLevel, msg: string, extra?: Readonly<Record<string, unknown>>): void => {
    const minLevel = LOG_LEVELS[getConfiguredLevel()];
    if (LOG_LEVELS[level] < minLevel) return;
    const entry = {
      ts: new Date().toISOString(),
      level,
      module,
      msg,
      ...redactExtra(extra),
    } satisfies LogEntry;

    process.stderr.write(JSON.stringify(entry) + "\n");
    for (const subscriber of logSubscribers) {
      subscriber(entry);
    }
  };

  return {
    debug: (msg, extra) => log("debug", msg, extra),
    info: (msg, extra) => log("info", msg, extra),
    warn: (msg, extra) => log("warn", msg, extra),
    error: (msg, extra) => log("error", msg, extra),
  };
};
