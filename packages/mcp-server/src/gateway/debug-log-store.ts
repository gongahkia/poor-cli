import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { resolveStatePath, subscribeLogEntries, type LogEntry } from "@dude/shared";

export type DebugLogSnapshot = {
  readonly enabled: boolean;
  readonly message: string;
  readonly observedAt: string;
  readonly entries: readonly LogEntry[];
  readonly totalEntries: number;
  readonly maxEntries: number;
  readonly logPath?: string;
  readonly limits: readonly string[];
};

export type DebugLogStore = {
  readonly enabled: boolean;
  readonly logPath?: string;
  readonly getSnapshot: (limit?: number) => DebugLogSnapshot;
};

const DEFAULT_LOG_PATH = "debug/rest-gateway.ndjson";
const DEFAULT_MAX_ENTRIES = 200;
const MAX_RESPONSE_ENTRIES = 500;
const DEBUG_LOG_LIMITS = [
  "Debug logs are redacted by key name before storage, but may still contain operational metadata.",
  "The endpoint is enabled only when DUDE_DEBUG_LOGS=1, SG_APIS_DEBUG_LOGS=1, or SG_APIS_LOG_LEVEL=debug.",
  "In production, /api/v1/debug/logs requires explicit workspace auth and an admin/debug-capable session.",
] as const;
const DEBUG_LOG_DISABLED_MESSAGE =
  "Debug log storage is disabled. Set DUDE_DEBUG_LOGS=1, SG_APIS_DEBUG_LOGS=1, or SG_APIS_LOG_LEVEL=debug to collect local redacted gateway logs.";
const DEBUG_LOG_ENABLED_MESSAGE =
  "Debug log storage is enabled. Entries are redacted by key name, but may still contain operational metadata.";

let activeStore: DebugLogStore | null = null;

const isTruthyEnv = (value: string | undefined): boolean =>
  value !== undefined && /^(1|true|yes|on)$/i.test(value.trim());

export const isDebugLogFlagEnabled = (
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean =>
  isTruthyEnv(env["DUDE_DEBUG_LOGS"])
  || isTruthyEnv(env["SG_APIS_DEBUG_LOGS"])
  || env["SG_APIS_LOG_LEVEL"]?.trim().toLowerCase() === "debug";

export const resolveDebugLogPath = (
  env: Readonly<Record<string, string | undefined>> = process.env,
): string => {
  const configured = env["DUDE_DEBUG_LOG_PATH"]?.trim() || env["SG_APIS_DEBUG_LOG_PATH"]?.trim();
  return configured !== undefined && configured !== ""
    ? resolve(configured)
    : resolveStatePath(DEFAULT_LOG_PATH);
};

const normalizeLimit = (limit: number | undefined): number => {
  if (limit === undefined || !Number.isFinite(limit)) {
    return DEFAULT_MAX_ENTRIES;
  }

  return Math.min(MAX_RESPONSE_ENTRIES, Math.max(1, Math.floor(limit)));
};

const parseLogEntry = (line: string): LogEntry | null => {
  try {
    const parsed = JSON.parse(line) as Partial<LogEntry>;
    if (
      typeof parsed.ts === "string"
      && typeof parsed.level === "string"
      && typeof parsed.module === "string"
      && typeof parsed.msg === "string"
    ) {
      return parsed as LogEntry;
    }
  } catch {
    return null;
  }
  return null;
};

export const readDebugLogEntries = (
  logPath: string,
  limit: number = DEFAULT_MAX_ENTRIES,
): { readonly entries: readonly LogEntry[]; readonly totalEntries: number } => {
  if (!existsSync(logPath)) {
    return { entries: [], totalEntries: 0 };
  }

  const lines = readFileSync(logPath, "utf8")
    .split(/\r?\n/)
    .filter((line) => line.trim() !== "");
  const normalizedLimit = normalizeLimit(limit);
  const entries = lines
    .slice(-normalizedLimit)
    .map(parseLogEntry)
    .filter((entry): entry is LogEntry => entry !== null);

  return {
    entries,
    totalEntries: lines.length,
  };
};

export const buildDisabledDebugLogSnapshot = (
  message = DEBUG_LOG_DISABLED_MESSAGE,
  source?: DebugLogSnapshot,
): DebugLogSnapshot => ({
  enabled: false,
  message,
  observedAt: new Date().toISOString(),
  entries: [],
  totalEntries: 0,
  maxEntries: source?.maxEntries ?? MAX_RESPONSE_ENTRIES,
  ...(source?.logPath === undefined ? {} : { logPath: source.logPath }),
  limits: source?.limits ?? DEBUG_LOG_LIMITS,
});

const appendDebugEntry = (logPath: string, entry: LogEntry): void => {
  try {
    mkdirSync(dirname(logPath), { recursive: true });
    appendFileSync(logPath, `${JSON.stringify(entry)}\n`, "utf8");
  } catch {
    // Debug logging must never break the gateway request path.
  }
};

export const initDebugLogStore = (): DebugLogStore => {
  if (activeStore !== null) {
    return activeStore;
  }

  const enabled = isDebugLogFlagEnabled();
  if (!enabled) {
    activeStore = {
      enabled: false,
      getSnapshot: () => buildDisabledDebugLogSnapshot(),
    };
    return activeStore;
  }

  const logPath = resolveDebugLogPath();
  mkdirSync(dirname(logPath), { recursive: true });
  subscribeLogEntries((entry) => appendDebugEntry(logPath, entry));

  activeStore = {
    enabled: true,
    logPath,
    getSnapshot: (limit) => {
      const { entries, totalEntries } = readDebugLogEntries(logPath, normalizeLimit(limit));
      return {
        enabled: true,
        message: DEBUG_LOG_ENABLED_MESSAGE,
        observedAt: new Date().toISOString(),
        entries,
        totalEntries,
        maxEntries: MAX_RESPONSE_ENTRIES,
        logPath,
        limits: DEBUG_LOG_LIMITS,
      };
    },
  };
  return activeStore;
};
