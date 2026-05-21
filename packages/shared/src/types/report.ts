export type ReportSectionId =
  | "executive_summary"
  | "coverage_matrix"
  | "risk_assessment"
  | "action_plan"
  | "identity_snapshot"
  | "evidence_records"
  | "supplemental_discovery"
  | "gaps"
  | "provenance"
  | "freshness"
  | "limits"
  | "manifest";

export type ReportWritingStyle =
  | "concise_analyst"
  | "audit_ready_formal"
  | "client_friendly_neutral"
  | "internal_escalation";

export type ReportExportFormat = "pdf" | "docx";

export type ReportTemplate = {
  readonly id: string;
  readonly name: string;
  readonly writingStyle: ReportWritingStyle;
  readonly sections: readonly ReportSectionId[];
};

export type ReportDocumentModel<TDossier = unknown, TMemo = unknown> = {
  readonly dossier: TDossier;
  readonly generatedAt: string;
  readonly memo?: TMemo;
  readonly template: ReportTemplate;
};
