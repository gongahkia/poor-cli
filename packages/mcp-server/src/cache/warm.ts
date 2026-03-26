import { createLogger } from "@sg-apis/shared";

const logger = createLogger("cache-warm");

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
        const { MasDataset } = await import("@sg-apis/shared");
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
        const { ensureLocalIndexWarm } = await import("../apis/datagov/client.js");
        ensureLocalIndexWarm();
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
