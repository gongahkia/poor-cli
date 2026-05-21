import { getDossierConfidence, sourceCoverageStatusLabel } from "@/lib/dossier";
import { getAnalystFollowUps } from "@/lib/next-checks";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";

export type ReportReadinessItemStatus = "ok" | "warning";

export type ReportReadinessItem = {
  id: "critical_followups" | "identity_confidence" | "source_availability" | "claim_citations";
  label: string;
  status: ReportReadinessItemStatus;
  detail: string;
  sourceRefs: string[];
};

export type ReportReadinessChecklistParams = {
  dossier: BusinessDossier;
  analystMemo?: AnalystMemoReady;
};

const sourceRef = (value: string): string => value.trim();

const hasExactIdentityConfidence = (dossier: BusinessDossier): boolean => {
  const confidence = getDossierConfidence(dossier);
  if (confidence?.identity?.level !== undefined && confidence.identity.level.trim() !== "") {
    return true;
  }
  return (dossier.matchConfidence ?? []).some((match) =>
    match.confidence === "exact" || match.confidence === "name-exact",
  );
};

const buildCriticalFollowUpItem = (dossier: BusinessDossier): ReportReadinessItem => {
  const critical = getAnalystFollowUps(dossier).filter((followUp) => followUp.priority === "critical");
  if (critical.length === 0) {
    return {
      detail: "No unresolved critical follow-ups were generated. Analysts should still review recommended and optional follow-ups.",
      id: "critical_followups",
      label: "Unresolved critical follow-ups",
      sourceRefs: [],
      status: "ok",
    };
  }
  return {
    detail: `${critical.length} critical follow-up${critical.length === 1 ? "" : "s"} need reviewer attention before handoff.`,
    id: "critical_followups",
    label: "Unresolved critical follow-ups",
    sourceRefs: critical.flatMap((followUp) => followUp.evidenceBasis.map((basis) => sourceRef(basis.ref))),
    status: "warning",
  };
};

const buildIdentityConfidenceItem = (dossier: BusinessDossier): ReportReadinessItem => {
  if (hasExactIdentityConfidence(dossier)) {
    return {
      detail: "Identity confidence metadata or exact match confidence is present.",
      id: "identity_confidence",
      label: "Identity confidence",
      sourceRefs: ["matchConfidence", "records.quality.dossierConfidence"],
      status: "ok",
    };
  }
  return {
    detail: "Identity confidence is missing or not exact. Confirm the ACRA identity row and identifier before relying on the handoff.",
    id: "identity_confidence",
    label: "Identity confidence",
    sourceRefs: ["matchConfidence", "records.quality.dossierConfidence"],
    status: "warning",
  };
};

const buildSourceAvailabilityItem = (dossier: BusinessDossier): ReportReadinessItem => {
  const unavailable = (dossier.sourceCoverage ?? []).filter((item) =>
    item.status === "unavailable" || item.status === "credential_blocked",
  );
  if (unavailable.length === 0) {
    return {
      detail: "No unavailable or credential-blocked source families were reported.",
      id: "source_availability",
      label: "Unavailable sources",
      sourceRefs: [],
      status: "ok",
    };
  }
  return {
    detail: unavailable
      .map((item) => `${item.label}: ${sourceCoverageStatusLabel(item.status)} - ${item.reason}`)
      .join("; "),
    id: "source_availability",
    label: "Unavailable sources",
    sourceRefs: unavailable.map((item) => `sourceCoverage.${item.family}`),
    status: "warning",
  };
};

const buildClaimCitationItem = (memo: AnalystMemoReady | undefined): ReportReadinessItem => {
  if (memo === undefined) {
    return {
      detail: "No cited analyst memo was included. Exported source facts remain available, but reviewer-written claims need citation review.",
      id: "claim_citations",
      label: "Uncited claims",
      sourceRefs: ["analystMemo"],
      status: "warning",
    };
  }
  const uncitedFindings = memo.evidenceMemo
    .map((finding, index) => ({ finding, index }))
    .filter(({ finding }) => finding.citationIds.length === 0);
  const uncitedRisk = memo.riskRating.citationIds.length === 0 ? ["riskRating"] : [];
  const rejectedClaims = memo.rejectedClaims.map((claim, index) => `rejectedClaims.${index + 1}:${claim.claim}`);
  const sourceRefs = [
    ...uncitedFindings.map(({ index }) => `evidenceMemo.${index + 1}`),
    ...uncitedRisk,
    ...rejectedClaims,
  ];
  if (sourceRefs.length === 0) {
    return {
      detail: "Generated memo findings and risk rating have citation references, and no rejected claims were returned.",
      id: "claim_citations",
      label: "Uncited claims",
      sourceRefs: memo.citations.map((citation) => citation.id),
      status: "ok",
    };
  }
  return {
    detail: [
      uncitedFindings.length === 0 ? null : `${uncitedFindings.length} memo finding${uncitedFindings.length === 1 ? "" : "s"} have no citation IDs`,
      uncitedRisk.length === 0 ? null : "risk rating has no citation IDs",
      rejectedClaims.length === 0 ? null : `${rejectedClaims.length} rejected claim${rejectedClaims.length === 1 ? "" : "s"} require review`,
    ].filter(Boolean).join("; "),
    id: "claim_citations",
    label: "Uncited claims",
    sourceRefs,
    status: "warning",
  };
};

export function buildReportReadinessChecklist({
  analystMemo,
  dossier,
}: ReportReadinessChecklistParams): ReportReadinessItem[] {
  return [
    buildCriticalFollowUpItem(dossier),
    buildIdentityConfidenceItem(dossier),
    buildSourceAvailabilityItem(dossier),
    buildClaimCitationItem(analystMemo),
  ];
}

export function reportReadinessSummary(items: readonly ReportReadinessItem[]): string {
  const warnings = items.filter((item) => item.status === "warning");
  if (warnings.length === 0) {
    return "No readiness warnings were generated. This is an analyst handoff state, not a clearance or approval decision.";
  }
  return `${warnings.length} readiness warning${warnings.length === 1 ? "" : "s"} require reviewer attention. This is not a pass/fail decision.`;
}
