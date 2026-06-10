import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  getCacheTtl,
  getRateLimit,
  getTimeout,
  loadConfig,
  parseMutableConfigValue,
  resetConfigCache,
  resolveOutputFormat,
} from "../config/index.js";

describe("config runtime accessors", () => {
  const originalHome = process.env["HOME"];
  const originalDudeDebugLogs = process.env["DUDE_DEBUG_LOGS"];
  const originalSgApisDebugLogs = process.env["SG_APIS_DEBUG_LOGS"];
  const originalSgApisLogLevel = process.env["SG_APIS_LOG_LEVEL"];
  let tempHome: string;

  beforeEach(() => {
    tempHome = mkdtempSync(join(tmpdir(), "sg-apis-config-"));
    process.env["HOME"] = tempHome;
    delete process.env["DUDE_DEBUG_LOGS"];
    delete process.env["SG_APIS_DEBUG_LOGS"];
    delete process.env["SG_APIS_LOG_LEVEL"];
    resetConfigCache();
  });

  afterEach(() => {
    if (originalHome === undefined) {
      delete process.env["HOME"];
    } else {
      process.env["HOME"] = originalHome;
    }
    if (originalDudeDebugLogs === undefined) {
      delete process.env["DUDE_DEBUG_LOGS"];
    } else {
      process.env["DUDE_DEBUG_LOGS"] = originalDudeDebugLogs;
    }
    if (originalSgApisDebugLogs === undefined) {
      delete process.env["SG_APIS_DEBUG_LOGS"];
    } else {
      process.env["SG_APIS_DEBUG_LOGS"] = originalSgApisDebugLogs;
    }
    if (originalSgApisLogLevel === undefined) {
      delete process.env["SG_APIS_LOG_LEVEL"];
    } else {
      process.env["SG_APIS_LOG_LEVEL"] = originalSgApisLogLevel;
    }

    resetConfigCache();
    rmSync(tempHome, { recursive: true, force: true });
  });

  it("reads runtime values from config file", () => {
    const configDir = join(tempHome, ".sg-apis");
    mkdirSync(configDir, { recursive: true });
    writeFileSync(
      join(configDir, "config.json"),
      JSON.stringify(
        {
          cache: { ttl: { DAILY: 120 } },
          rateLimits: { mas: { maxTokens: 7, refillPerSecond: 1.5 } },
          timeouts: { mas: 4321 },
          defaultFormat: "json",
        },
        null,
        2,
      ),
    );

    expect(getCacheTtl("DAILY")).toBe(120);
    expect(getRateLimit("mas")).toEqual({ maxTokens: 7, refillPerSecond: 1.5 });
    expect(getTimeout("mas")).toBe(4321);
    expect(resolveOutputFormat(undefined)).toBe("json");
    expect(loadConfig()).toMatchObject({
      cache: { ttl: { DAILY: 120 } },
      rateLimits: { mas: { maxTokens: 7, refillPerSecond: 1.5 } },
      timeouts: { mas: 4321 },
      defaultFormat: "json",
    });
  });

  it("parses supported mutable config keys", () => {
    expect(parseMutableConfigValue("timeouts.mas", "1500")).toBe(1500);
    expect(parseMutableConfigValue("rateLimits.mas.refillPerSecond", "1.5")).toBe(1.5);
    expect(parseMutableConfigValue("defaultFormat", "csv")).toBe("csv");
  });

  it("enables debug log level when debug log storage is enabled", () => {
    process.env["DUDE_DEBUG_LOGS"] = "1";
    resetConfigCache();

    expect(loadConfig().logLevel).toBe("debug");
  });

  it("keeps explicit log level above debug storage default", () => {
    process.env["DUDE_DEBUG_LOGS"] = "1";
    process.env["SG_APIS_LOG_LEVEL"] = "warn";
    resetConfigCache();

    expect(loadConfig().logLevel).toBe("warn");
  });

  it("rejects unsupported or invalid config values", () => {
    expect(() => parseMutableConfigValue("unsupported.key", "1")).toThrow("Unsupported config key");
    expect(() => parseMutableConfigValue("defaultFormat", "xml")).toThrow("Invalid value");
    expect(() => parseMutableConfigValue("timeouts.mas", "0")).toThrow("positive integer");
  });
});
