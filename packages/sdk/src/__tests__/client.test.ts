import { describe, expect, it } from "vitest";
import type { SweeApiError } from "../index.js";
import { SweeClient } from "../index.js";

const okFetch = (handler: (url: string, init: RequestInit) => unknown): typeof fetch =>
  (async (url, init) => {
    const body = handler(String(url), init ?? {});
    return new Response(JSON.stringify(body), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    });
  }) as typeof fetch;

describe("SweeClient", () => {
  it("calls the Pulse snapshot tool and unwraps gateway data", async () => {
    const seen: { url?: string; body?: unknown; authorization?: string | null } = {};
    const client = new SweeClient({
      baseUrl: "https://swee.example",
      token: "test-token",
      fetch: okFetch((url, init) => {
        seen.url = url;
        seen.body = JSON.parse(String(init.body));
        seen.authorization = new Headers(init.headers).get("authorization");

        return {
          data: {
            snapshot: {
              generatedAt: "2026-05-22T00:00:00.000Z",
              focus: "all",
              signals: [],
              sourceHealth: [],
              gaps: [],
            },
          },
          shield: { auditId: "audit-1" },
        };
      }),
    });

    const snapshot = await client.pulseSnapshot({ focus: "all" });

    expect(seen.url).toBe("https://swee.example/api/v1/swee_pulse_snapshot");
    expect(seen.body).toEqual({ focus: "all" });
    expect(seen.authorization).toBe("Bearer test-token");
    expect(snapshot.generatedAt).toBe("2026-05-22T00:00:00.000Z");
  });

  it("calls weather and mobility Pulse tools", async () => {
    const seen: string[] = [];
    const client = new SweeClient({
      baseUrl: "https://swee.example",
      fetch: okFetch((url) => {
        seen.push(url);
        return { data: { signals: [], sourceHealth: [], gaps: [] } };
      }),
    });

    await client.pulseWeather({ area: "Bedok" });
    await client.pulseMobility();

    expect(seen).toEqual([
      "https://swee.example/api/v1/swee_pulse_weather",
      "https://swee.example/api/v1/swee_pulse_mobility",
    ]);
  });

  it("calls deterministic Pulse explain", async () => {
    const client = new SweeClient({
      fetch: okFetch(() => ({
        data: {
          snapshot: { generatedAt: "2026-05-22T00:00:00.000Z", focus: null, signals: [], sourceHealth: [], gaps: [] },
          explanation: "Swee Pulse observed 0 source-backed signals.",
          aiUsed: false,
        },
      })),
    });

    await expect(client.pulseExplain()).resolves.toMatchObject({
      aiUsed: false,
      explanation: expect.stringContaining("Swee Pulse"),
    });
  });

  it("calls Shield audit and scanner tools", async () => {
    const seen: string[] = [];
    const client = new SweeClient({
      baseUrl: "https://swee.example",
      fetch: okFetch((url) => {
        seen.push(url);
        if (url.endsWith("swee_shield_scan_tools")) {
          return { data: { findings: [], scannedTools: 84 } };
        }
        return { data: { records: [] } };
      }),
    });

    await expect(client.shieldAudits({ limit: 5 })).resolves.toEqual({ records: [] });
    await expect(client.shieldScan()).resolves.toEqual({ findings: [], scannedTools: 84 });
    expect(seen).toEqual([
      "https://swee.example/api/v1/swee_shield_audit_lookup",
      "https://swee.example/api/v1/swee_shield_scan_tools",
    ]);
  });

  it("raises typed gateway errors", async () => {
    const client = new SweeClient({
      fetch: (async () =>
        new Response(JSON.stringify({ error: { message: "No such tool" } }), {
          headers: { "Content-Type": "application/json" },
          status: 404,
        })) as typeof fetch,
    });

    await expect(client.callTool("missing_tool", {})).rejects.toMatchObject({
      name: "SweeApiError",
      status: 404,
      message: "No such tool",
    } satisfies Partial<SweeApiError>);
  });
});
