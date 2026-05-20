import { describe, expect, it } from "vitest";
import type { DudeApiError } from "../index.js";
import { DudeClient } from "../index.js";

const okFetch = (handler: (url: string, init: RequestInit) => unknown): typeof fetch =>
  (async (url, init) => {
    const body = handler(String(url), init ?? {});
    return new Response(JSON.stringify(body), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    });
  }) as typeof fetch;

describe("DudeClient", () => {
  it("calls the CDD orchestrator for product reports", async () => {
    const seen: { url?: string; body?: unknown } = {};
    const client = new DudeClient({
      baseUrl: "https://dude.example",
      fetch: okFetch((url, init) => {
        seen.url = url;
        seen.body = JSON.parse(String(init.body));

        return {
          dossier: {
            title: "Business dossier",
            summary: [],
            evidence: [],
            records: {},
            gaps: [],
            provenance: [],
            freshness: [],
            limits: [],
          },
          generatedAt: "2026-05-20T00:00:00.000Z",
          memo: { status: "unavailable" },
          orchestration: { status: "ready" },
          peopleDiscovery: { configured: false },
          webPresence: { configured: false },
        };
      }),
    });

    const report = await client.cddReport({ uen: "201900001A" });

    expect(seen.url).toBe("https://dude.example/api/v1/dude/cdd-orchestrator");
    expect(seen.body).toEqual({ uen: "201900001A" });
    expect(report.dossier.title).toBe("Business dossier");
    expect(report.orchestration).toEqual({ status: "ready" });
  });

  it("calls the business dossier tool and unwraps gateway records", async () => {
    const seen: { url?: string; body?: unknown; authorization?: string | null } = {};
    const client = new DudeClient({
      baseUrl: "https://dude.example",
      token: "test-token",
      fetch: okFetch((url, init) => {
        seen.url = url;
        seen.body = JSON.parse(String(init.body));
        seen.authorization = new Headers(init.headers).get("authorization");

        return {
          data: {
            record: {
              title: "Business dossier",
              summary: [],
              evidence: [],
              records: {},
              gaps: [],
              provenance: [],
              freshness: [],
              limits: [],
            },
          },
        };
      }),
    });

    const dossier = await client.businessDossier({
      uen: "201900001A",
      includeContextIds: true,
    });

    expect(seen.url).toBe("https://dude.example/api/v1/sg_business_dossier");
    expect(seen.body).toEqual({ uen: "201900001A", includeContextIds: true });
    expect(seen.authorization).toBe("Bearer test-token");
    expect(dossier.title).toBe("Business dossier");
  });

  it("validates business dossier identifiers before calling the gateway", async () => {
    let called = false;
    const client = new DudeClient({
      fetch: okFetch(() => {
        called = true;
        return {};
      }),
    });

    await expect(client.businessDossier({ includeContextIds: true })).rejects.toThrow(
      "Provide at least one business or estate-agent identifier.",
    );
    expect(called).toBe(false);
  });

  it("raises typed gateway errors", async () => {
    const client = new DudeClient({
      fetch: (async () =>
        new Response(JSON.stringify({ error: { message: "No such tool" } }), {
          headers: { "Content-Type": "application/json" },
          status: 404,
        })) as typeof fetch,
    });

    await expect(client.callTool("missing_tool", {})).rejects.toMatchObject({
      name: "DudeApiError",
      status: 404,
      message: "No such tool",
    } satisfies Partial<DudeApiError>);
  });
});
