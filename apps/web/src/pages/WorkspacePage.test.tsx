import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const appSource = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");

describe("App CDD-only shell", () => {
  it("routes to the search form, counterparty CDD run, and browser-local case view", () => {
    expect(appSource).toContain('path="/"');
    expect(appSource).toContain('path="/c/:identifier"');
    expect(appSource).toContain('path="/case/:caseId"');
    expect(appSource).not.toContain("WorkspacePage");
    expect(appSource).not.toContain("ToastProvider");
    expect(appSource).not.toContain("lazy(");
  });
});
