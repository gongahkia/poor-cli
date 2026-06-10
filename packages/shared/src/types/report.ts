export type ReportSectionId =
  | "review_metadata"
  | "readiness_checklist"
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

export type ReportReviewerMetadata = {
  readonly preparedBy: string;
  readonly reviewedBy: string;
  readonly reviewDate: string;
  readonly caseStatus: string;
  readonly internalReference: string;
  readonly reportPurpose: string;
};

export type ReportTemplate = {
  readonly id: string;
  readonly name: string;
  readonly writingStyle: ReportWritingStyle;
  readonly sections: readonly ReportSectionId[];
  readonly metadata: ReportReviewerMetadata;
};

export type ReportDocumentModel<TDossier = unknown, TMemo = unknown> = {
  readonly dossier: TDossier;
  readonly generatedAt: string;
  readonly memo?: TMemo;
  readonly template: ReportTemplate;
};
