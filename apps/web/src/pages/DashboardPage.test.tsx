import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "@/App";
import { DashboardPage, ShieldAuditTable } from "@/pages/DashboardPage";

describe("DashboardPage", () => {
  it("renders the Swee SG dashboard shell without CDD copy", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(html).toContain("Swee SG");
    expect(html).toContain("What matters now");
    expect(html).toContain("Coverage Gaps");
    expect(html).toContain("Runtime Evidence");
    expect(html).toContain("Security Workbench");
    expect(html).toContain("Investigation Pack");
    expect(html).toContain("Policy Simulator");
    expect(html).toContain("Needs Attention");
    expect(html).toContain("Mobility");
    expect(html).toContain("Weather");
    expect(html).toContain("Source Health");
    expect(html).toContain("Normal Weather Coverage");
    expect(html).toContain("Ops: Human Approvals");
    expect(html).toContain("Ops: Shield Audit");
    expect(html).not.toContain("Dude CDD");
    expect(html).not.toContain("CDD case");
    expect(html).not.toContain("counterparty");
  });

  it("keeps the active app surface on the dashboard route", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(html).toContain("Swee SG");
    expect(html).not.toContain("Running CDD orchestrator");
  });

  it("renders Shield audit findings, reason codes, and hash evidence", () => {
    const html = renderToStaticMarkup(
      <ShieldAuditTable
        audits={[{
          auditId: "12345678-aaaa-bbbb-cccc-123456789012",
          decision: { decision: "warn", reasonCodes: ["policy_warn_list"], riskLevel: "medium" },
          durationMs: 42,
          outputHash: "abcdef1234567890",
          rawOutputHash: "123456abcdef7890",
          runtimeFindings: [{ action: "neutralized", code: "SECRET_EXFILTRATION_NEUTRALIZED", severity: "critical" }],
          startedAt: "2026-06-10T02:00:00.000Z",
          status: "success",
          toolName: "splunk_search",
        }]}
      />,
    );

    expect(html).toContain("critical neutralized");
    expect(html).toContain("policy_warn_list");
    expect(html).toContain("raw:123456ab");
    expect(html).toContain("post:abcdef12");
  });
});
