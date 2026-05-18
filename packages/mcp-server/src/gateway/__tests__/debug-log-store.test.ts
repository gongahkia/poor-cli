import { describe, expect, it } from "vitest";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import {
  buildDisabledDebugLogSnapshot,
  isDebugLogFlagEnabled,
  readDebugLogEntries,
  resolveDebugLogPath,
} from "../debug-log-store.js";

describe("debug log store helpers", () => {
  it("enables debug storage from Dude, SG, or debug-level flags", () => {
    expect(isDebugLogFlagEnabled({})).toBe(false);
    expect(isDebugLogFlagEnabled({ DUDE_DEBUG_LOGS: "1" })).toBe(true);
    expect(isDebugLogFlagEnabled({ SG_APIS_DEBUG_LOGS: "true" })).toBe(true);
    expect(isDebugLogFlagEnabled({ SG_APIS_LOG_LEVEL: "debug" })).toBe(true);
    expect(isDebugLogFlagEnabled({ DUDE_DEBUG_LOGS: "0", SG_APIS_LOG_LEVEL: "info" })).toBe(false);
  });

  it("uses the explicit debug log path when configured", () => {
    expect(resolveDebugLogPath({ DUDE_DEBUG_LOG_PATH: "/tmp/dude-debug.ndjson" })).toBe("/tmp/dude-debug.ndjson");
    expect(resolveDebugLogPath({ SG_APIS_DEBUG_LOG_PATH: "/tmp/sg-debug.ndjson" })).toBe("/tmp/sg-debug.ndjson");
  });

  it("reads the latest valid log entries from an NDJSON file", () => {
    const tempDir = mkdtempSync(join(tmpdir(), "dude-debug-logs-"));
    try {
      const logPath = join(tempDir, "gateway.ndjson");
      mkdirSync(tempDir, { recursive: true });
      writeFileSync(
        logPath,
        [
          JSON.stringify({ ts: "2026-05-17T00:00:00.000Z", level: "info", module: "a", msg: "one" }),
          "not-json",
          JSON.stringify({ ts: "2026-05-17T00:00:01.000Z", level: "warn", module: "b", msg: "two" }),
          JSON.stringify({ ts: "2026-05-17T00:00:02.000Z", level: "error", module: "c", msg: "three" }),
        ].join("\n"),
      );

      const result = readDebugLogEntries(logPath, 2);

      expect(result.totalEntries).toBe(4);
      expect(result.entries.map((entry) => entry.msg)).toEqual(["two", "three"]);
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it("builds an explicit disabled response without exposing stored entries", () => {
    const snapshot = buildDisabledDebugLogSnapshot(
      "Debug log access is disabled for this production mode.",
      {
        enabled: true,
        message: "Debug log storage is enabled.",
        observedAt: "2026-05-18T00:00:00.000Z",
        entries: [
          { ts: "2026-05-18T00:00:00.000Z", level: "info", module: "gateway", msg: "stored" },
        ],
        totalEntries: 1,
        maxEntries: 500,
        limits: ["debug limits"],
      },
    );

    expect(snapshot.enabled).toBe(false);
    expect(snapshot.message).toContain("disabled");
    expect(snapshot.entries).toEqual([]);
    expect(snapshot.totalEntries).toBe(0);
  });
});
