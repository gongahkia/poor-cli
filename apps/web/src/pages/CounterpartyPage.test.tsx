import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("./CounterpartyPage.tsx", import.meta.url), "utf8");

describe("CounterpartyPage orchestrator loading", () => {
  it("loads the initial dossier from one CDD orchestrator response", () => {
    expect(source).toContain("/api/v1/dude/cdd-orchestrator");
    expect(source).toContain("toWebPresenceState(orchestration.webPresence)");
    expect(source).toContain("toPeopleDiscoveryState(orchestration.peopleDiscovery)");
    expect(source).toContain("toAnalystMemoState(orchestration.memo)");
    expect(source).not.toContain("callTool<BusinessDossier>(\n      \"sg_business_dossier\",\n      buildBusinessDossierInput(decodedIdentifier)");
  });

  it("keeps legacy supplemental fetches guarded away from the initial orchestrated load", () => {
    const guardCount = source.match(/if \(isUsingInitialOrchestration\)/g)?.length ?? 0;
    expect(guardCount).toBeGreaterThanOrEqual(3);
    expect(source).toContain("/api/v1/dude/web-presence");
    expect(source).toContain("/api/v1/dude/people-discovery");
    expect(source).toContain("/api/v1/dude/memo");
  });
});
