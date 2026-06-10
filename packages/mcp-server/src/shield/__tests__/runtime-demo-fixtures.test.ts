import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { ShieldAuditStore, setShieldAuditStoreForTesting } from "../audit-store.js";
import { invokeShieldedTool } from "../enforcement.js";
import type { RegisteredToolDefinition } from "../../tools/tool-definition.js";

const fixturePath = resolve(
  import.meta.dirname,
  "../../upstreams/splunk/__tests__/fixtures/demo-events.json",
);

const readFixture = (): Readonly<Record<string, unknown>> =>
  JSON.parse(readFileSync(fixturePath, "utf8")) as Readonly<Record<string, unknown>>;

describe("Splunk demo runtime fixtures", () => {
  afterEach(() => {
    setShieldAuditStoreForTesting(null);
  });

  it("defends synthetic Splunk events without a live Splunk token", async () => {
    setShieldAuditStoreForTesting(new ShieldAuditStore(":memory:"));
    const fixture = readFixture();
    const tool = {
      name: "splunk_search",
      description: "Run bounded Splunk search.",
      surface: "operational",
      inputSchema: {},
      annotations: { readOnlyHint: true, openWorldHint: true },
      handler: async () => ({
        content: [{ type: "text", text: JSON.stringify(fixture) }],
        structuredContent: { fixture },
      }),
    } satisfies RegisteredToolDefinition;

    const result = await invokeShieldedTool(tool, { query: "index=security sourcetype=synthetic:*" });
    const text = result.content[0]?.type === "text" ? result.content[0].text : "";

    expect(text).toContain("Synthetic Splunk demo events");
    expect(text).toContain("[redacted-email]");
    expect(text).toContain("Bearer [redacted]");
    expect(text).toContain("[neutralized prompt-injection text]");
    expect(text).not.toContain("sk-demo1234567890");
    expect(result.shieldAudit.runtimeFindings.length).toBeGreaterThanOrEqual(5);
    expect(result.shieldAudit.rawOutputHash).not.toBe(result.shieldAudit.outputHash);
  });
});
