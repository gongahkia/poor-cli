const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 } as const;
type LogLevel = keyof typeof LOG_LEVELS;

export type Logger = {
  readonly debug: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly info: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly warn: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
  readonly error: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
};

const getConfiguredLevel = (): LogLevel => {
  const env = process.env["SG_APIS_LOG_LEVEL"];
  if (env !== undefined && env !== "" && env in LOG_LEVELS) {
    return env as LogLevel;
  }
  return "info";
};

export const createLogger = (module: string): Logger => {
  const minLevel = LOG_LEVELS[getConfiguredLevel()];

  const log = (level: LogLevel, msg: string, extra?: Readonly<Record<string, unknown>>): void => {
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
