import { createLogger } from "@swee-sg/shared";

const logger = createLogger("cache-warm");
const DEFAULT_WARM_INTERVAL_MS = 15 * 60 * 1000;

export type WarmResult = {
  readonly warmed: readonly string[];
  readonly failed: readonly string[];
  readonly durationMs: number;
};

export const warmCache = async (): Promise<WarmResult> => {
  const start = Date.now();
  const warmed: string[] = [];
  const failed: string[] = [];

  const tasks = [
    {
      name: "mas_exchange_rates",
      fn: async () => {
        const { query } = await import("../apis/mas/client.js");
        const { MasDataset } = await import("@swee-sg/shared");
        await query(MasDataset.EXCHANGE_RATES, { limit: 10 });
      },
    },
    {
      name: "singstat_popular",
      fn: async () => {
        const { searchDatasets } = await import("../apis/singstat/client.js");
        await searchDatasets("GDP", 5);
      },
    },
    {
      name: "datagov_index",
      fn: async () => {
        const { buildLocalIndex } = await import("../apis/datagov/client.js");
        await buildLocalIndex();
      },
    },
    {
      name: "datagov_datastore_probe",
      fn: async () => {
        const { probeAcraLookupReadiness } = await import("../apis/acra/client.js");
        await probeAcraLookupReadiness();
      },
    },
  ];

  const results = await Promise.allSettled(tasks.map((t) => t.fn()));

  for (let i = 0; i < tasks.length; i++) {
    const task = tasks[i]!;
    const result = results[i]!;
    if (result.status === "fulfilled") {
      warmed.push(task.name);
    } else {
      failed.push(task.name);
      logger.warn("warm-up failed", { task: task.name, error: result.reason });
    }
  }

  const durationMs = Date.now() - start;
  logger.info("cache warm-up complete", { warmed: warmed.length, failed: failed.length, durationMs });

  return { warmed, failed, durationMs };
};

const parseWarmIntervalMs = (): number => {
  const configured =
    process.env["DUDE_CACHE_WARM_INTERVAL_MS"]
    ?? process.env["SG_APIS_CACHE_WARM_INTERVAL_MS"];
  if (configured === undefined || configured.trim() === "") {
    return DEFAULT_WARM_INTERVAL_MS;
  }
  const value = Number(configured);
  if (!Number.isFinite(value) || value < 0) {
    logger.warn("invalid cache warm interval, using default", { configured });
    return DEFAULT_WARM_INTERVAL_MS;
  }
  return value;
};

export const startCacheWarmScheduler = (): (() => void) => {
  const intervalMs = parseWarmIntervalMs();
  if (intervalMs === 0) {
    logger.info("periodic cache warm-up disabled");
    return () => undefined;
  }

  let scheduledWarmInFlight = false;
  const timer = setInterval(() => {
    if (scheduledWarmInFlight) {
      logger.warn("skipping cache warm-up because previous run is still active");
      return;
    }
    scheduledWarmInFlight = true;
    void warmCache()
      .catch((error: unknown) => {
        logger.warn("scheduled cache warm-up failed", {
          error: error instanceof Error ? error.message : String(error),
        });
      })
      .finally(() => {
        scheduledWarmInFlight = false;
      });
  }, intervalMs);
  timer.unref();
  logger.info("periodic cache warm-up scheduled", { intervalMs });

  return () => clearInterval(timer);
};
