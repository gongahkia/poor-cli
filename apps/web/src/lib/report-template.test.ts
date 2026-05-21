import { describe, expect, it } from "vitest";

import {
  DEFAULT_REPORT_TEMPLATE,
  REPORT_SECTION_PRESETS,
  REPORT_WRITING_STYLE_DESCRIPTIONS,
  applyReportSectionPreset,
  moveReportSection,
  toggleReportSection,
  updateReportReviewerMetadata,
} from "@/lib/report-template";

describe("report templates", () => {
  it("keeps the default report as an analyst handoff with metadata and readiness first", () => {
    expect(DEFAULT_REPORT_TEMPLATE.sections.slice(0, 4)).toEqual([
      "review_metadata",
      "readiness_checklist",
      "executive_summary",
      "coverage_matrix",
    ]);
    expect(DEFAULT_REPORT_TEMPLATE.metadata.reportPurpose).toBe("CDD analyst handoff");
    expect(REPORT_WRITING_STYLE_DESCRIPTIONS.concise_analyst).toContain("internal triage");
  });

  it("applies section presets with explicit ordering and writing style", () => {
    const preset = REPORT_SECTION_PRESETS.find((item) => item.id === "supplemental_evidence_review");
    const template = applyReportSectionPreset(DEFAULT_REPORT_TEMPLATE, "supplemental_evidence_review");

    expect(preset).toBeDefined();
    expect(template.name).toBe("Supplemental evidence review");
    expect(template.writingStyle).toBe("internal_escalation");
    expect(template.sections.slice(0, 4)).toEqual([
      "review_metadata",
      "readiness_checklist",
      "supplemental_discovery",
      "action_plan",
    ]);
    expect(template.sections.at(-1)).toBe("manifest");
  });

  it("supports section selection, ordering, and reviewer metadata updates", () => {
    const withoutLimits = toggleReportSection(DEFAULT_REPORT_TEMPLATE.sections, "limits");
    expect(withoutLimits).not.toContain("limits");
    expect(toggleReportSection(withoutLimits, "executive_summary")).toContain("executive_summary");

    const moved = moveReportSection(DEFAULT_REPORT_TEMPLATE.sections, "risk_assessment", "up");
    expect(moved.indexOf("risk_assessment")).toBe(DEFAULT_REPORT_TEMPLATE.sections.indexOf("risk_assessment") - 1);

    const template = updateReportReviewerMetadata(DEFAULT_REPORT_TEMPLATE, {
      internalReference: "CDD-2026-001",
      preparedBy: "Analyst A",
    });
    expect(template.metadata.preparedBy).toBe("Analyst A");
    expect(template.metadata.internalReference).toBe("CDD-2026-001");
    expect(DEFAULT_REPORT_TEMPLATE.metadata.preparedBy).toBe("");
  });
});
