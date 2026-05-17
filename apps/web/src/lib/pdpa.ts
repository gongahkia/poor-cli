import type { BusinessDossier, BriefProvenanceItem } from "@/types/dossier";
import {
  confidenceLabel,
  formatTimestamp,
  getSummaryString,
} from "@/lib/dossier";

export type PdpaChecklistStatus = "evidence_available" | "analyst_action" | "blocked_by_gap";

export type PdpaChecklistCitation = {
  id: string;
  label: string;
  url: string;
};

export type PdpaChecklistItem = {
  id: string;
  title: string;
  obligation: string;
  status: PdpaChecklistStatus;
  sourceSection: string;
  evidence: string[];
  gaps: string[];
  action: string;
  citations: PdpaChecklistCitation[];
};

export type PdpaChecklistReport = {
  title: string;
  generatedAt: string;
  entityName: string | null;
  uen: string | null;
  items: PdpaChecklistItem[];
  citations: PdpaChecklistCitation[];
  nonAdviceNotice: string;
};

export const pdpaCitations = {
  obligations: {
    id: "PDPC-DPO",
    label: "PDPC Data Protection Obligations",
    url: "https://www.pdpc.gov.sg/overview-of-pdpa/the-legislation/personal-data-protection-act/data-protection-obligations",
  },
  keyConcepts: {
    id: "PDPC-KEY",
    label: "PDPC Advisory Guidelines on Key Concepts in the PDPA",
    url: "https://www.pdpc.gov.sg/guidelines-and-consultation/2020/03/advisory-guidelines-on-key-concepts-in-the-personal-data-protection-act",
  },
  dataIntermediaries: {
    id: "PDPC-DI",
    label: "PDPC distinction between organisations and data intermediaries",
    url: "https://www.pdpc.gov.sg/the-distinction-between-organisations-and-data-intermediaries-and-why-it-matters",
  },
  commonLapses: {
    id: "PDPC-LAPSES-2026",
    label: "PDPC Advisory on Common Data Protection Lapses and Recommended Measures",
    url: "https://www.pdpc.gov.sg/help-and-resources/2026/01/advisory-on-common-data-protection-lapses-and-recommended-measures",
  },
} satisfies Record<string, PdpaChecklistCitation>;

const OFFICIAL_SOURCES = new Set(["ACRA", "BCA", "CEA", "GeBIZ", "BOA", "HSA", "HLB"]);

const formatSource = (item: BriefProvenanceItem): string => {
  const parts = [
    item.source,
    item.coverage,
    `${item.recordCount} records`,
    item.authRequired ? "auth required" : "no auth",
    item.sourceUrl === undefined ? null : item.sourceUrl,
  ].filter(Boolean);
  return parts.join("; ");
};

const hasOfficialIdentity = (dossier: BusinessDossier): boolean => {
  const matchedModules = dossier.records.resolution?.matchedModules ?? [];
  return matchedModules.includes("acra") || dossier.provenance.some((item) => item.source === "ACRA" && item.recordCount > 0);
};

const hasBlockingGaps = (dossier: BusinessDossier): boolean =>
  dossier.gaps.some((gap) => /UNAVAILABLE|FAILED|TIMEOUT|RATE/i.test(`${gap.code} ${gap.message}`));

const moduleEvidence = (dossier: BusinessDossier): string[] => {
  const matchedModules = dossier.records.resolution?.matchedModules ?? [];
  if (matchedModules.length === 0) {
    return ["No matched sector modules were returned by the dossier."];
  }
  return [`Matched dossier modules: ${matchedModules.map((module) => module.toUpperCase()).join(", ")}.`];
};

const provenanceEvidence = (dossier: BusinessDossier): string[] => {
  const official = dossier.provenance.filter((item) => OFFICIAL_SOURCES.has(item.source));
  if (official.length === 0) {
    return ["No official registry provenance was returned."];
  }
  return official.map(formatSource);
};

const freshnessEvidence = (dossier: BusinessDossier): string[] => {
  if (dossier.freshness.length === 0) {
    return ["No freshness metadata was returned."];
  }
  return dossier.freshness.map((item) => {
    const observed = formatTimestamp(item.observedAt) ?? item.observedAt;
    const upstream = formatTimestamp(item.upstreamTimestamp ?? null) ?? "not provided";
    return `${item.source}: observed ${observed}; upstream timestamp ${upstream}.`;
  });
};

const confidenceEvidence = (dossier: BusinessDossier): string[] => {
  const confidence = dossier.matchConfidence ?? [];
  if (confidence.length === 0) {
    return ["No match-confidence details were returned."];
  }
  return confidence.map((item) => {
    const suffix = item.matchedOn === null ? "" : ` on ${item.matchedOn}`;
    return `${item.source}: ${confidenceLabel(item.confidence)}${suffix}.`;
  });
};

const gapMessages = (dossier: BusinessDossier): string[] =>
  dossier.gaps.length === 0
    ? []
    : dossier.gaps.map((gap) => `${gap.code}: ${gap.message}`);

export function buildPdpaChecklist(dossier: BusinessDossier): PdpaChecklistItem[] {
  const officialIdentity = hasOfficialIdentity(dossier);
  const blockingGaps = hasBlockingGaps(dossier);
  const gaps = gapMessages(dossier);
  const entityName = getSummaryString(dossier, "Entity");
  const uen = getSummaryString(dossier, "UEN");

  return [
    {
      id: "identity-accuracy",
      title: "Vendor identity and data accuracy",
      obligation: "Accuracy Obligation",
      status: officialIdentity && !blockingGaps ? "evidence_available" : blockingGaps ? "blocked_by_gap" : "analyst_action",
      sourceSection: "PDPC Accuracy Obligation and Key Concepts Chapter 16",
      evidence: [
        entityName === null ? "Entity name was not present in the dossier summary." : `Entity: ${entityName}.`,
        uen === null ? "UEN was not present in the dossier summary." : `UEN: ${uen}.`,
        ...confidenceEvidence(dossier),
        ...provenanceEvidence(dossier),
      ],
      gaps,
      action: "Confirm the contracting party against the official entity name/UEN before relying on the vendor record.",
      citations: [pdpaCitations.obligations, pdpaCitations.keyConcepts],
    },
    {
      id: "protection-controls",
      title: "Security arrangements for personal data",
      obligation: "Section 24 / Protection Obligation",
      status: blockingGaps ? "blocked_by_gap" : "analyst_action",
      sourceSection: "PDPA section 24, PDPC Protection Obligation, and 2026 common-lapses advisory",
      evidence: [
        ...moduleEvidence(dossier),
        ...provenanceEvidence(dossier).slice(0, 4),
      ],
      gaps: [
        ...gaps,
        "Public registry evidence does not prove the vendor's access controls, encryption, vulnerability management, staff controls, or incident monitoring.",
      ],
      action: "Request the vendor's security measures, data-flow diagram, access-control summary, incident process, and recent security evidence before onboarding personal-data processing.",
      citations: [pdpaCitations.obligations, pdpaCitations.commonLapses],
    },
    {
      id: "retention-deletion",
      title: "Retention and deletion controls",
      obligation: "Retention Limitation Obligation",
      status: "analyst_action",
      sourceSection: "PDPC Retention Limitation Obligation and Key Concepts Chapter 18",
      evidence: [
        ...freshnessEvidence(dossier),
        "Dude exports preserve dossier provenance/freshness for downstream audit review.",
      ],
      gaps: [
        "The public dossier does not state how long the vendor retains customer personal data or how deletion is evidenced.",
      ],
      action: "Collect the vendor retention schedule, deletion procedure, backup expiry period, and exit/return process.",
      citations: [pdpaCitations.obligations, pdpaCitations.keyConcepts],
    },
    {
      id: "transfer-limitation",
      title: "Cross-border transfer and subprocessors",
      obligation: "Section 26 / Transfer Limitation Obligation",
      status: "analyst_action",
      sourceSection: "PDPA section 26, PDPC Transfer Limitation Obligation, and Key Concepts Chapter 19",
      evidence: [
        ...provenanceEvidence(dossier).slice(0, 3),
        "The dossier identifies public registry sources used for vendor diligence but does not certify hosting countries or subprocessor controls.",
      ],
      gaps: [
        "The public dossier does not identify the vendor's data hosting regions, overseas support access, subprocessors, or transfer safeguards.",
      ],
      action: "Ask the vendor for processing locations, subprocessor list, overseas support countries, transfer safeguards, and customer notice process.",
      citations: [pdpaCitations.obligations, pdpaCitations.keyConcepts],
    },
    {
      id: "data-intermediary-boundary",
      title: "Controller / data-intermediary boundary",
      obligation: "Data intermediary accountability",
      status: "analyst_action",
      sourceSection: "PDPC guidance on organisations and data intermediaries",
      evidence: [
        "The dossier can support vendor identity and public-source checks before deciding the contractual processing role.",
        ...moduleEvidence(dossier),
      ],
      gaps: [
        "The dossier does not decide whether the vendor is acting as an organisation, data intermediary, joint controller, or independent professional adviser for the customer's workflow.",
      ],
      action: "Document the processing role in the contract/DPA and map which party handles notification, access/correction, breach, protection, retention, and transfer controls.",
      citations: [pdpaCitations.dataIntermediaries, pdpaCitations.obligations],
    },
    {
      id: "breach-notification",
      title: "Breach notification and escalation path",
      obligation: "Data Breach Notification Obligation",
      status: "analyst_action",
      sourceSection: "PDPC Data Breach Notification Obligation",
      evidence: [
        "Dossier gaps and limits are preserved so upstream evidence failures are visible to reviewers.",
        ...freshnessEvidence(dossier).slice(0, 3),
      ],
      gaps: [
        "The public dossier does not provide the vendor's breach notification contact, incident severity levels, or notification timelines.",
      ],
      action: "Record the vendor security contact, DPO/privacy contact, breach-notification SLA, and customer escalation path.",
      citations: [pdpaCitations.obligations, pdpaCitations.commonLapses],
    },
  ];
}

export function buildPdpaChecklistReport(
  dossier: BusinessDossier,
  generatedAt = new Date(),
): PdpaChecklistReport {
  const items = buildPdpaChecklist(dossier);
  const citations = Array.from(
    new Map(items.flatMap((item) => item.citations).map((citation) => [citation.id, citation])).values(),
  );

  return {
    title: `PDPA vendor diligence checklist - ${dossier.title}`,
    generatedAt: generatedAt.toISOString(),
    entityName: getSummaryString(dossier, "Entity"),
    uen: getSummaryString(dossier, "UEN"),
    items,
    citations,
    nonAdviceNotice:
      "This checklist is a public-data diligence aid for analyst review. It is not legal advice, a PDPA compliance opinion, or a substitute for vendor contracts, counsel review, or DPO assessment.",
  };
}

export function pdpaStatusLabel(status: PdpaChecklistStatus): string {
  if (status === "evidence_available") {
    return "Evidence available";
  }
  if (status === "blocked_by_gap") {
    return "Blocked by dossier gap";
  }
  return "Analyst action";
}
