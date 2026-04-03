import { describe, it, expect, afterEach } from "vitest";
import { join } from "node:path";
import { homedir } from "node:os";
import { resolveStatePath } from "../state-dir.js";

describe("resolveStatePath", () => {
  const originalEnv = process.env["SG_APIS_STATE_DIR"];

  afterEach(() => {
    if (originalEnv === undefined) {
      delete process.env["SG_APIS_STATE_DIR"];
    } else {
      process.env["SG_APIS_STATE_DIR"] = originalEnv;
    }
  });

  it("uses default ~/.sg-apis when env is unset", () => {
    delete process.env["SG_APIS_STATE_DIR"];
    expect(resolveStatePath("cache.db")).toBe(join(homedir(), ".sg-apis", "cache.db"));
  });

  it("respects SG_APIS_STATE_DIR override", () => {
    process.env["SG_APIS_STATE_DIR"] = "/var/lib/sg-apis";
    expect(resolveStatePath("cache.db")).toBe("/var/lib/sg-apis/cache.db");
  });

  it("joins arbitrary filenames under the root", () => {
    process.env["SG_APIS_STATE_DIR"] = "/tmp/test-state";
    expect(resolveStatePath("artifacts.db")).toBe("/tmp/test-state/artifacts.db");
    expect(resolveStatePath("keys.db")).toBe("/tmp/test-state/keys.db");
    expect(resolveStatePath("config.json")).toBe("/tmp/test-state/config.json");
  });
});
