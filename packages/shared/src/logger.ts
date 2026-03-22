import { loadConfig } from "./config/index.js";

const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 } as const;
type LogLevel = keyof typeof LOG_LEVELS;

export type Logger = {
  readonly debug: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly info: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly warn: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly error: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
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
  const log = (level: LogLevel, msg: string, extra?: Readonly<Record<string, unknown>>): void => {
    const minLevel = LOG_LEVELS[getConfiguredLevel()];
    if (LOG_LEVELS[level] < minLevel) return;
    const entry = {
      ts: new Date().toISOString(),
      level,
      module,
      msg,
      ...extra,
    };
    process.stderr.write(JSON.stringify(entry) + "\n");
  };

  return {
    debug: (msg, extra) => log("debug", msg, extra),
    info: (msg, extra) => log("info", msg, extra),
    warn: (msg, extra) => log("warn", msg, extra),
    error: (msg, extra) => log("error", msg, extra),
  };
};
