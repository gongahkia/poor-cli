import { describe, expect, it } from "vitest";
import { ShieldAuditStore, setShieldAuditStoreForTesting } from "../audit-store.js";
import { invokeShieldedTool } from "../enforcement.js";
import type { RegisteredToolDefinition } from "../../tools/tool-definition.js";

describe("Swee Shield enforcement", () => {
  it("prevents denied handlers from running", async () => {
    const previousMode = process.env["SWEE_SHIELD_MODE"];
    process.env["SWEE_SHIELD_MODE"] = "kiasu";
    setShieldAuditStoreForTesting(new ShieldAuditStore(":memory:"));
    let invoked = false;
    const tool = {
      name: "sg_cache_clear",
      description: "Clear cache entries.",
      surface: "operational",
      inputSchema: {},
      annotations: { destructiveHint: true },
      handler: async () => {
        invoked = true;
        return { content: [{ type: "text", text: "cleared" }] };
      },
    } satisfies RegisteredToolDefinition;

    const result = await invokeShieldedTool(tool, {}, { traceId: "trace-deny" });

    expect(invoked).toBe(false);
    expect(result.isError).toBe(true);
    expect(result.shieldAudit.status).toBe("denied");
    expect(result.structuredContent?.["shield"]).toBeDefined();
    setShieldAuditStoreForTesting(null);
    if (previousMode === undefined) {
      delete process.env["SWEE_SHIELD_MODE"];
    } else {
      process.env["SWEE_SHIELD_MODE"] = previousMode;
    }
  });
});
