import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  FileDown,
  FileText,
  ListChecks,
  SearchCheck,
  ShieldAlert,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { AnalystMemoSection, type AnalystMemoState } from "@/components/dossier/AnalystMemoSection";
import { ConfidenceSection } from "@/components/dossier/ConfidenceSection";
import { EvidenceSection, type ModuleFollowUpRequest, type RunningBusinessModule } from "@/components/dossier/EvidenceSection";
import { FollowUpInputView, FollowUpResultView } from "@/components/dossier/FollowUpResultView";
import { GapsSection } from "@/components/dossier/GapsSection";
import { HandoffSection } from "@/components/dossier/HandoffSection";
import { NextChecksSection } from "@/components/dossier/NextChecksSection";
import { PdpaChecklistSection } from "@/components/dossier/PdpaChecklistSection";
import { PeopleDiscoverySection, type PeopleDiscoveryState } from "@/components/dossier/PeopleDiscoverySection";
import { ProvenanceSection } from "@/components/dossier/ProvenanceSection";
import { ReportPreview } from "@/components/dossier/ReportPreview";
import { RiskSection } from "@/components/dossier/RiskSection";
import { SnapshotSection } from "@/components/dossier/SnapshotSection";
import { SourceUseWarningsSection } from "@/components/dossier/SourceUseWarningsSection";
import { SupplementalEvidencePanel } from "@/components/dossier/SupplementalEvidencePanel";
import { WebPresenceSection, type WebPresenceState } from "@/components/dossier/WebPresenceSection";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DEFAULT_REPORT_TEMPLATE,
  REPORT_SECTION_PRESETS,
  REPORT_SECTION_DESCRIPTIONS,
  REPORT_SECTION_LABELS,
  REPORT_WRITING_STYLE_DESCRIPTIONS,
  REPORT_WRITING_STYLE_LABELS,
  applyReportSectionPreset,
  moveReportSection,
  toggleReportSection,
  updateReportReviewerMetadata,
  type ReportExportFormat,
  type ReportTemplate,
  type ReportWritingStyle,
} from "@/lib/report-template";
import { callTool } from "@/lib/api/client";
import { BUSINESS_MODULE_LABELS, getSummaryString, type FollowUpBusinessModule } from "@/lib/dossier";
import { followUpCategoryLabel, followUpPriorityLabel, getAnalystFollowUps } from "@/lib/next-checks";
import { cn } from "@/lib/utils";
import type { AnalystMemoCitation, AnalystMemoReady } from "@/types/analyst-memo";
import type { AnalystFollowUp, BusinessDossier, BusinessDossierModule, NextCheck } from "@/types/dossier";
import type { CddOrchestrationTrace, CddOrchestratorStage } from "@/types/orchestration";

type DossierFindingsTabsProps = {
  dossier: BusinessDossier;
  isPdpaExporting: boolean;
  memoState: AnalystMemoState;
  onExportPdpaReport: (reviewedItemIds: readonly string[]) => void;
  onExportReport?: (template: ReportTemplate, format: ReportExportFormat) => void;
  onModuleFollowUp: (request: ModuleFollowUpRequest) => void;
  orchestration?: CddOrchestrationTrace;
  peopleDiscoveryState: PeopleDiscoveryState;
  rerunningModule: RunningBusinessModule;
  sharedMemoState: string | null;
  webPresenceState: WebPresenceState;
};

type EvidenceDialogState =
  | { kind: "citation"; citation: AnalystMemoCitation }
  | { kind: "pack"; title: string; description: string }
  | {
      kind: "followUp";
      description: string;
      error?: string;
      input: Record<string, unknown>;
      moduleRequest?: ModuleFollowUpRequest;
      result?: unknown;
      status: "idle" | "running" | "ready" | "error";
      title: string;
      tool: string;
    }
  | null;

type DossierReportTab = "summary" | "evidence" | "report";

type SupportedFollowUpAction = {
  description: string;
  label: string;
  linkPattern: RegExp;
  module?: FollowUpBusinessModule;
  tool: string;
};

type ConfidenceBlockerDetail = {
  detail: string;
  label: string;
  source: string;
};

type OverviewSegment = {
  citation?: AnalystMemoCitation;
  text: string;
};

type EvidenceStats = {
  gaps: number;
  provenance: number;
  records: number;
};

const stageToneClassName: Record<CddOrchestratorStage["status"], string> = {
  blocked: "border-destructive/30 bg-destructive/5 text-destructive",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-900",
  skipped: "border-border bg-muted/50 text-muted-foreground",
  unavailable: "border-amber-200 bg-amber-50 text-amber-900",
};

function OrchestrationTracePanel({ orchestration }: { orchestration?: CddOrchestrationTrace }) {
  if (orchestration === undefined) return null;
  const stages = orchestration.stages ?? [];
  return (
    <section className="rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-foreground">CDD orchestrator trace</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            One run from ACRA identity through sector modules, supplemental review, and memo generation.
          </p>
        </div>
        <span className="w-fit rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
          {orchestration.status === "ready" ? "Ready" : "Identity not resolved"}
        </span>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {stages.map((stage) => (
          <article className="rounded-md border border-border bg-background p-3" key={stage.id}>
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-semibold text-foreground">{stage.label}</h3>
              <span className={cn(
                "w-fit shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize",
                stageToneClassName[stage.status],
              )}>
                {stage.status}
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">{stage.detail}</p>
          </article>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Official modules: {orchestration.officialModules.join(", ") || "none"}. Supplemental tools: {orchestration.supplementalTools.join(", ") || "none"}.
      </p>
    </section>
  );
}

const writingStyles: ReportWritingStyle[] = [
  "concise_analyst",
  "audit_ready_formal",
  "client_friendly_neutral",
  "internal_escalation",
];

const dossierReportTabs: { id: DossierReportTab; label: string; description: string }[] = [
  {
    description: "Read the cited findings, risk context, blockers, and next actions.",
    id: "summary",
    label: "Summary",
  },
  {
    description: "Inspect records, provenance, freshness, gaps, limits, and source detail.",
    id: "evidence",
    label: "Evidence Pack",
  },
  {
    description: "Choose sections, writing preset, and export the review artifact.",
    id: "report",
    label: "Report Builder",
  },
];

const supportedFollowUpActions: readonly SupportedFollowUpAction[] = [
  {
    description: "Dude can rerun the retained ACRA entity lookup by UEN or company name for source-level registry rows.",
    label: "ACRA entity details",
    linkPattern: /full ACRA entity details|ACRA entity details|ACRA/i,
    tool: "sg_acra_entities",
  },
  {
    description: "Dude can run OpenSanctions candidate screening when the licensed API key is configured. Results are analyst-review candidates, not a regulated determination.",
    label: "OpenSanctions",
    linkPattern: /OpenSanctions|sanctions\/watchlist|sanctions|watchlist/i,
    tool: "sg_sanctions_screen",
  },
  {
    description: "Dude can cross-link candidate OpenCorporates identifiers without treating them as ownership or control evidence.",
    label: "OpenCorporates",
    linkPattern: /OpenCorporates identifiers|OpenCorporates|Cross-link/i,
    tool: "sg_opencorporates_links",
  },
  {
    description: "Dude can search bounded official Singapore public feeds for keyword evidence. This is not general web monitoring or unsupported sentiment analysis.",
    label: "official Singapore public feeds",
    linkPattern: /official Singapore public feeds|keyword evidence|official public feeds|public feeds/i,
    tool: "sg_adverse_media_lite",
  },
  {
    description: "Dude can build a shallow graph from the supplied public dossier records, with strict limits against ownership or control claims.",
    label: "shallow graph",
    linkPattern: /shallow graph|relationship graph/i,
    tool: "sg_relationship_graph",
  },
  {
    description: "Dude can rerun the GeBIZ procurement module for tender-award evidence linked to this counterparty.",
    label: "GeBIZ",
    linkPattern: /GeBIZ|procurement/i,
    module: "gebiz",
    tool: "sg_gebiz_tenders",
  },
];

const toolModuleFollowUps: Partial<Record<string, FollowUpBusinessModule>> = {
  sg_bca_licensed_builders: "bca",
  sg_bca_registered_contractors: "bca",
  sg_boa_architects: "boa",
  sg_boa_architecture_firms: "boa",
  sg_cea_salespersons: "cea",
  sg_gebiz_tenders: "gebiz",
  sg_hlb_hotels: "hlb",
  sg_hsa_health_product_licensees: "hsa",
  sg_hsa_licensed_pharmacies: "hsa",
};

const genericBlockerPatterns = [
  /^missing evidence that blocks confidence\.?$/i,
  /^missing evidence or upstream gap\.?$/i,
  /^missing evidence$/i,
];

function uniqueStrings(values: readonly string[]): string[] {
  return Array.from(new Set(values.filter((value) => value.trim() !== "").map((value) => value.trim())));
}

function getDefaultFollowUpValue(dossier: BusinessDossier): string {
  return getSummaryString(dossier, "Entity")
    ?? getSummaryString(dossier, "UEN")
    ?? dossier.title;
}

function getDossierIdentity(dossier: BusinessDossier): { entity: string; uen: string | null; status: string | null } {
  return {
    entity: getSummaryString(dossier, "Entity") ?? dossier.title,
    status: getSummaryString(dossier, "Entity status") ?? getSummaryString(dossier, "Status"),
    uen: getSummaryString(dossier, "UEN"),
  };
}

function buildSupportedToolInput(
  tool: string,
  dossier: BusinessDossier,
  nextCheck?: Pick<NextCheck, "input"> | Pick<AnalystFollowUp, "input">,
): Record<string, unknown> {
  const identity = getDossierIdentity(dossier);
  const entityOrUen = identity.entity !== "" ? identity.entity : identity.uen ?? dossier.title;
  if (tool === "sg_acra_entities") {
    return identity.uen === null ? { entityName: identity.entity, limit: 10 } : { uen: identity.uen, limit: 10 };
  }
  if (tool === "sg_sanctions_screen") {
    return { name: entityOrUen, ...(identity.uen === null ? {} : { uen: identity.uen }) };
  }
  if (tool === "sg_opencorporates_links") {
    return {
      entityName: entityOrUen,
      jurisdictionCode: "sg",
      ...(identity.uen === null ? {} : { uen: identity.uen }),
    };
  }
  if (tool === "sg_adverse_media_lite") {
    return { keyword: entityOrUen };
  }
  if (tool === "sg_relationship_graph") {
    return { records: dossier.records };
  }
  return nextCheck?.input ?? {};
}

function extractFollowUpValue(input: Record<string, unknown> | undefined, fallback: string): string {
  if (input !== undefined) {
    for (const key of ["entityName", "companyName", "supplierName", "keeperName", "pharmacyName", "name", "uen"]) {
      const value = input[key];
      if (typeof value === "string" && value.trim() !== "") {
        return value.trim();
      }
    }
  }
  return fallback;
}

function actionForTool(tool: string): SupportedFollowUpAction | null {
  const known = supportedFollowUpActions.find((action) => action.tool === tool);
  if (known !== undefined) return known;
  const module = toolModuleFollowUps[tool];
  if (module === undefined) return null;
  return {
    description: `Dude can rerun the ${BUSINESS_MODULE_LABELS[module]} sector module and refresh the dossier evidence pack.`,
    label: BUSINESS_MODULE_LABELS[module],
    linkPattern: new RegExp(BUSINESS_MODULE_LABELS[module], "i"),
    module,
    tool,
  };
}

function normalizeText(value: string): string {
  return value.toLowerCase().replace(/\s+/g, " ").trim();
}

function findNextCheckForStep(step: string, dossier: BusinessDossier): NextCheck | undefined {
  const normalizedStep = normalizeText(step);
  return (dossier.nextChecks ?? []).find((check) => {
    const normalizedReason = normalizeText(check.reason);
    return normalizedReason === normalizedStep
      || normalizedReason.includes(normalizedStep)
      || normalizedStep.includes(normalizedReason)
      || normalizedStep.includes(normalizeText(check.tool));
  });
}

function findAnalystFollowUpForStep(step: string, dossier: BusinessDossier): AnalystFollowUp | undefined {
  const normalizedStep = normalizeText(step);
  return getAnalystFollowUps(dossier).find((followUp) => {
    const normalizedAction = normalizeText(followUp.action);
    const normalizedReason = normalizeText(followUp.reason);
    return normalizedAction === normalizedStep
      || normalizedAction.includes(normalizedStep)
      || normalizedStep.includes(normalizedAction)
      || normalizedReason.includes(normalizedStep)
      || normalizedStep.includes(normalizedReason)
      || (followUp.tool !== undefined && normalizedStep.includes(normalizeText(followUp.tool)));
  });
}

function findFollowUpAction(step: string, dossier: BusinessDossier): { action: SupportedFollowUpAction; nextCheck?: NextCheck } | null {
  const analystFollowUp = findAnalystFollowUpForStep(step, dossier);
  if (analystFollowUp?.tool !== undefined) {
    const directAction = actionForTool(analystFollowUp.tool);
    if (directAction !== null) return { action: directAction, nextCheck: analystFollowUp as NextCheck };
  }
  const nextCheck = findNextCheckForStep(step, dossier);
  if (nextCheck !== undefined) {
    const directAction = actionForTool(nextCheck.tool);
    if (directAction !== null) return { action: directAction, nextCheck };
  }
  const patternAction = supportedFollowUpActions.find((action) => action.linkPattern.test(step));
  return patternAction === undefined ? null : { action: patternAction, nextCheck };
}

function renderLinkedFollowUpText(
  step: string,
  action: SupportedFollowUpAction | null,
  onClick: () => void,
): ReactNode {
  if (action === null) return step;
  const match = action.linkPattern.exec(step);
  if (match === null) return step;
  const before = step.slice(0, match.index);
  const linked = match[0];
  const after = step.slice(match.index + linked.length);
  return (
    <>
      {before}
      <button
        className="inline rounded-sm font-medium text-primary underline underline-offset-4 transition hover:text-primary/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
        onClick={onClick}
        type="button"
      >
        {linked}
      </button>
      {after}
    </>
  );
}

function buildFollowUpDialogState(params: {
  action: SupportedFollowUpAction;
  dossier: BusinessDossier;
  nextCheck?: NextCheck;
  step: string;
}): NonNullable<EvidenceDialogState> {
  const input = buildSupportedToolInput(params.action.tool, params.dossier, params.nextCheck);
  const module = params.action.module ?? toolModuleFollowUps[params.action.tool];
  const moduleRequest = module === undefined
    ? undefined
    : {
        module,
        value: extractFollowUpValue(params.nextCheck?.input, getDefaultFollowUpValue(params.dossier)),
      };

  return {
    description: `${params.action.description} Triggered from follow-up: ${params.step}`,
    input,
    kind: "followUp",
    moduleRequest,
    status: "idle",
    title: params.action.label,
    tool: params.action.tool,
  };
}

function isGenericBlocker(value: string): boolean {
  return genericBlockerPatterns.some((pattern) => pattern.test(value.trim()));
}

function pushUniqueBlocker(
  rows: ConfidenceBlockerDetail[],
  seen: Set<string>,
  row: ConfidenceBlockerDetail,
): void {
  const key = `${row.label}:${row.detail}`;
  if (seen.has(key)) return;
  seen.add(key);
  rows.push(row);
}

function buildConfidenceBlockers(dossier: BusinessDossier, memo: AnalystMemoReady): ConfidenceBlockerDetail[] {
  const rows: ConfidenceBlockerDetail[] = [];
  const seen = new Set<string>();
  const memoBlockers = uniqueStrings([
    ...memo.decisionAid.confidenceBlockers,
    ...memo.riskRating.confidenceBlockers,
  ]);
  const hadGenericBlocker = memoBlockers.some(isGenericBlocker);

  memoBlockers
    .filter((blocker) => !isGenericBlocker(blocker))
    .forEach((blocker) => pushUniqueBlocker(rows, seen, {
      detail: blocker,
      label: "Memo blocker",
      source: "AI memo",
    }));

  dossier.gaps.forEach((gap) => pushUniqueBlocker(rows, seen, {
    detail: gap.message,
    label: gap.code,
    source: "Dossier gap",
  }));

  (dossier.records.resolution?.moduleReasons ?? [])
    .filter((reason) => reason.status === "skipped" || reason.status === "unsearched")
    .forEach((reason) => pushUniqueBlocker(rows, seen, {
      detail: reason.reason,
      label: `${BUSINESS_MODULE_LABELS[reason.module]} ${reason.status}`,
      source: "Resolver",
    }));

  if (rows.length === 0 && hadGenericBlocker) {
    pushUniqueBlocker(rows, seen, {
      detail: "The memo provider returned a generic blocker without source-specific detail. Review the Evidence Pack gaps, provenance, freshness, and limits before relying on this draft.",
      label: "Generic model blocker",
      source: "AI memo",
    });
  }

  if (rows.length === 0 && dossier.limits.length > 0) {
    dossier.limits.slice(0, 3).forEach((limit) => pushUniqueBlocker(rows, seen, {
      detail: limit.message,
      label: limit.code,
      source: "Dossier limit",
    }));
  }

  return rows.slice(0, 8);
}

function stringifyCitationValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function addCitationIfMissing(
  map: Map<string, AnalystMemoCitation>,
  citation: AnalystMemoCitation,
): void {
  if (!map.has(citation.id)) {
    map.set(citation.id, citation);
  }
}

function buildCitationMap(
  dossier: BusinessDossier,
  memo: AnalystMemoReady,
  peopleDiscoveryState?: PeopleDiscoveryState,
  webPresenceState?: WebPresenceState,
): Map<string, AnalystMemoCitation> {
  const map = new Map(memo.citations.map((citation) => [citation.id, citation]));
  dossier.summary.forEach((item, index) => addCitationIfMissing(map, {
    id: `summary-${index + 1}`,
    label: item.label,
    source: item.source ?? "summary",
    text: `${item.label}: ${stringifyCitationValue(item.value)}`,
  }));
  dossier.evidence.forEach((item, index) => addCitationIfMissing(map, {
    id: `evidence-${index + 1}`,
    label: item.label,
    source: item.source ?? "evidence",
    text: `${item.label}: ${stringifyCitationValue(item.value)}`,
  }));
  (dossier.riskFlags ?? []).forEach((flag, index) => addCitationIfMissing(map, {
    id: `risk-${index + 1}`,
    label: flag.code,
    source: flag.source,
    text: `${flag.severity}: ${flag.message}`,
  }));
  dossier.gaps.forEach((gap, index) => addCitationIfMissing(map, {
    id: `gap-${index + 1}`,
    label: gap.code,
    source: "gap",
    text: gap.message,
  }));
  dossier.limits.forEach((limit, index) => addCitationIfMissing(map, {
    id: `limit-${index + 1}`,
    label: limit.code,
    source: "limit",
    text: limit.message,
  }));
  dossier.provenance.forEach((item, index) => addCitationIfMissing(map, {
    id: `provenance-${index + 1}`,
    label: item.source,
    source: item.tool,
    text: `${item.coverage} Records: ${item.recordCount}. Auth required: ${item.authRequired ? "yes" : "no"}.`,
  }));
  if (webPresenceState?.status === "success") {
    const presence = webPresenceState.presence;
    if (presence.possibleOfficialWebsite !== null) {
      addCitationIfMissing(map, {
        id: "web-presence-official",
        label: "Possible official website",
        source: "TinyFish Search",
        text: presence.possibleOfficialWebsite,
      });
    }
    presence.results.slice(0, 5).forEach((result, index) => addCitationIfMissing(map, {
      id: `web-presence-${index + 1}`,
      label: result.title,
      source: result.siteName ?? result.url,
      text: `${result.title}: ${result.snippet} (${result.url})`,
    }));
    presence.limits.forEach((limit, index) => addCitationIfMissing(map, {
      id: `web-presence-limit-${index + 1}`,
      label: "Web presence limit",
      source: "TinyFish Search",
      text: limit,
    }));
  }
  if (peopleDiscoveryState?.status === "success") {
    const discovery = peopleDiscoveryState.discovery;
    discovery.results.slice(0, 5).forEach((result, index) => addCitationIfMissing(map, {
      id: `people-discovery-${index + 1}`,
      label: result.title,
      source: result.siteName ?? result.url,
      text: `${result.title}: ${result.snippet} (${result.url})`,
    }));
    discovery.suggestedActions.forEach((action, index) => addCitationIfMissing(map, {
      id: `people-discovery-action-${index + 1}`,
      label: "People discovery action",
      source: "TinyFish Search",
      text: action,
    }));
    discovery.limits.forEach((limit, index) => addCitationIfMissing(map, {
      id: `people-discovery-limit-${index + 1}`,
      label: "People discovery limit",
      source: "TinyFish Search",
      text: limit,
    }));
  }
  return map;
}

function findCitation(
  citations: ReadonlyMap<string, AnalystMemoCitation>,
  predicate: (citation: AnalystMemoCitation) => boolean,
): AnalystMemoCitation | undefined {
  return Array.from(citations.values()).find(predicate);
}

function findSummaryCitation(
  citations: ReadonlyMap<string, AnalystMemoCitation>,
  label: string,
): AnalystMemoCitation | undefined {
  return findCitation(citations, (citation) =>
    citation.id.startsWith("summary-") && citation.label.toLowerCase() === label.toLowerCase());
}

function findGapCitation(
  citations: ReadonlyMap<string, AnalystMemoCitation>,
  pattern: RegExp,
): AnalystMemoCitation | undefined {
  return findCitation(citations, (citation) =>
    citation.id.startsWith("gap-") && (pattern.test(citation.label) || pattern.test(citation.text)));
}

function findAnyCitation(
  citations: ReadonlyMap<string, AnalystMemoCitation>,
  pattern: RegExp,
): AnalystMemoCitation | undefined {
  return findCitation(citations, (citation) =>
    pattern.test(citation.id) || pattern.test(citation.label) || pattern.test(citation.source) || pattern.test(citation.text));
}

function formatModuleList(modules: readonly string[] | undefined): string {
  if (modules === undefined || modules.length === 0) return "no official modules";
  return modules.map((module) => BUSINESS_MODULE_LABELS[module as BusinessDossierModule] ?? module.toUpperCase()).join(", ");
}

const SUPPLEMENTAL_EVIDENCE_PACKS: readonly {
  readonly label: string;
  readonly pattern: RegExp;
}[] = [
  { label: "sanctions screen", pattern: /sanctions|opensanctions|sg_sanctions_screen/i },
  { label: "OpenCorporates links", pattern: /opencorporates|corporates|sg_opencorporates_links/i },
  { label: "adverse-media lite", pattern: /adverse media|adverse-media|official[- ]feed|sg_adverse_media_lite/i },
  { label: "relationship graph", pattern: /relationship graph|sg_relationship_graph/i },
];

function getSupplementalEvidencePackSegments(
  dossier: BusinessDossier,
  citations: ReadonlyMap<string, AnalystMemoCitation>,
): readonly OverviewSegment[] {
  if (!Array.isArray(dossier.records.externalDiligence) || dossier.records.externalDiligence.length === 0) {
    return [];
  }
  const foundPacks = SUPPLEMENTAL_EVIDENCE_PACKS
    .map((pack) => ({
      citation: findAnyCitation(citations, pack.pattern),
      label: pack.label,
      pattern: pack.pattern,
    }))
    .filter((pack) => pack.citation !== undefined || dossier.records.externalDiligence?.some((record) =>
      typeof record.title === "string" && pack.pattern.test(record.title)));

  return foundPacks.map((pack, index) => {
    const text = `${index === 0 ? "" : index === foundPacks.length - 1 ? " and " : ", "}${pack.label}`;
    return pack.citation === undefined ? { text } : { citation: pack.citation, text };
  });
}

function getSupplementalDiscoveryPackSegments(
  peopleDiscoveryState: PeopleDiscoveryState | undefined,
  webPresenceState: WebPresenceState | undefined,
  citations: ReadonlyMap<string, AnalystMemoCitation>,
): readonly OverviewSegment[] {
  const packs: { label: string; citation?: AnalystMemoCitation }[] = [];
  if (
    webPresenceState?.status === "success"
    && (webPresenceState.presence.configured || webPresenceState.presence.results.length > 0 || webPresenceState.presence.limits.length > 0)
  ) {
    const citation = findAnyCitation(citations, /web-presence|possible official website|web presence limit|tinyfish/i);
    packs.push(citation === undefined ? { label: "web presence" } : { citation, label: "web presence" });
  }
  if (
    peopleDiscoveryState?.status === "success"
    && (peopleDiscoveryState.discovery.configured || peopleDiscoveryState.discovery.results.length > 0 || peopleDiscoveryState.discovery.limits.length > 0)
  ) {
    const citation = findAnyCitation(citations, /people-discovery|people discovery/i);
    packs.push(citation === undefined ? { label: "people discovery" } : { citation, label: "people discovery" });
  }
  return packs.map((pack, index) => {
    const text = `${index === 0 ? "" : index === packs.length - 1 ? " and " : ", "}${pack.label}`;
    return pack.citation === undefined ? { text } : { citation: pack.citation, text };
  });
}

function buildExecutiveOverviewSegments(
  dossier: BusinessDossier,
  memo: AnalystMemoReady,
  citations: ReadonlyMap<string, AnalystMemoCitation>,
  peopleDiscoveryState?: PeopleDiscoveryState,
  webPresenceState?: WebPresenceState,
): OverviewSegment[] {
  const identity = getDossierIdentity(dossier);
  const entityCitation = findSummaryCitation(citations, "Entity");
  const uenCitation = findSummaryCitation(citations, "UEN");
  const statusCitation = findSummaryCitation(citations, "Entity status") ?? findSummaryCitation(citations, "Status");
  const riskCitation = memo.riskRating.citationIds
    .map((id) => citations.get(id))
    .find((citation): citation is AnalystMemoCitation => citation !== undefined)
    ?? findCitation(citations, (citation) => citation.id.startsWith("risk-"));
  const sanctionsGap = findGapCitation(citations, /opensanctions|sanctions|watchlist/i);
  const corporatesGap = findGapCitation(citations, /opencorporates|corporates/i);
  const matchedModules = dossier.records.resolution?.matchedModules ?? [];
  const searchedModules = dossier.records.resolution?.searchedModules ?? [];
  const blockers = buildConfidenceBlockers(dossier, memo);
  const providerGaps = [sanctionsGap, corporatesGap].filter((citation): citation is AnalystMemoCitation => citation !== undefined);
  const genericBlocker = blockers.find((blocker) => /API|credential|license|licence|configured/i.test(blocker.detail));
  const supplementalPacks = getSupplementalEvidencePackSegments(dossier, citations);
  const discoveryPacks = getSupplementalDiscoveryPackSegments(peopleDiscoveryState, webPresenceState, citations);
  const segment = (text: string, citation?: AnalystMemoCitation): OverviewSegment => ({ citation, text });
  const segments: OverviewSegment[] = [
    segment(identity.entity, entityCitation),
  ];

  if (identity.uen !== null) {
    segments.push(segment(" (UEN "), segment(identity.uen, uenCitation), segment(")"));
  }

  segments.push(segment(" is an ACRA-matched Singapore entity"));
  if (identity.status !== null) {
    segments.push(segment(", with ACRA recording its current status as "));
    segments.push(segment(identity.status, statusCitation));
  }
  segments.push(segment(". "));
  segments.push(segment("For analyst review, the practical issue is the status finding: this dossier should be treated as "));
  segments.push(segment(`${memo.riskRating.level} risk`, riskCitation));
  segments.push(segment(" for any new or ongoing engagement until the business context and intended use are confirmed. "));
  segments.push(segment(`The current run is strongest on identity evidence: Dude searched ${formatModuleList(searchedModules)} and matched ${formatModuleList(matchedModules)}.`));

  if (supplementalPacks.length > 0) {
    segments.push(segment(" The executive view also incorporates supplemental evidence packs for "));
    segments.push(...supplementalPacks);
    segments.push(segment("."));
  }

  if (discoveryPacks.length > 0) {
    segments.push(segment(" Supplemental discovery inputs include "));
    segments.push(...discoveryPacks);
    segments.push(segment("."));
  }

  if (providerGaps.length > 0) {
    segments.push(segment(" Supplemental screening is not yet complete because "));
    providerGaps.forEach((citation, index) => {
      if (index > 0) segments.push(segment(index === providerGaps.length - 1 ? " and " : ", "));
      segments.push(segment(citation.label, citation));
    });
    segments.push(segment(" remain unavailable or require configured provider access."));
  } else if (genericBlocker !== undefined) {
    segments.push(segment(` ${genericBlocker.detail}`));
  } else if (blockers.length > 0) {
    segments.push(segment(` The main blocker is ${blockers[0].detail}`));
  }

  segments.push(segment(" Recommended follow-up is to verify the full ACRA record, then review any source gaps, limits, and supplemental pack results that remain unresolved."));
  return segments;
}

function buildEvidenceStats(dossier: BusinessDossier): EvidenceStats {
  return {
    gaps: dossier.gaps.length,
    provenance: dossier.provenance.length,
    records: Object.values(dossier.records)
      .reduce((sum, value) => sum + (Array.isArray(value) ? value.length : 0), 0),
  };
}

function EvidenceLink({
  citation,
  children,
  onOpenEvidence,
}: {
  citation: AnalystMemoCitation;
  children: ReactNode;
  onOpenEvidence: (state: EvidenceDialogState) => void;
}) {
  return (
    <button
      className="inline break-words font-semibold text-foreground underline decoration-muted-foreground/40 underline-offset-4 transition hover:text-primary hover:decoration-primary"
      data-citation-id={citation.id}
      onClick={() => onOpenEvidence({ citation, kind: "citation" })}
      type="button"
    >
      {children}
    </button>
  );
}

function EvidenceLinkedText({
  onOpenEvidence,
  segments,
}: {
  onOpenEvidence: (state: EvidenceDialogState) => void;
  segments: readonly OverviewSegment[];
}) {
  return (
    <>
      {segments.map((segment, index) => segment.citation === undefined ? (
        <span key={`${segment.text}-${index}`}>{segment.text}</span>
      ) : (
        <EvidenceLink citation={segment.citation} key={`${segment.text}-${segment.citation.id}-${index}`} onOpenEvidence={onOpenEvidence}>
          {segment.text}
        </EvidenceLink>
      ))}
    </>
  );
}

function SummaryFallback({ dossier }: { dossier: BusinessDossier }) {
  return (
    <div className="space-y-3">
      {dossier.summary.slice(0, 6).map((item) => (
        <button
          className="block w-full rounded-md border border-border bg-background p-3 text-left transition hover:bg-muted/50"
          key={`${item.label}-${item.source ?? ""}`}
          type="button"
        >
          <span className="block text-xs font-medium uppercase text-muted-foreground">{item.label}</span>
          <span className="mt-1 block break-words text-sm text-foreground">
            {item.value === null || item.value === undefined || item.value === "" ? "-" : String(item.value)}
          </span>
          {item.source === undefined || item.source === null ? null : (
            <span className="mt-1 block text-xs text-muted-foreground">Source: {item.source}</span>
          )}
        </button>
      ))}
    </div>
  );
}

function CitedSummary({
  dossier,
  memoState,
  onOpenEvidence,
  peopleDiscoveryState,
  webPresenceState,
}: {
  dossier: BusinessDossier;
  memoState: AnalystMemoState;
  onOpenEvidence: (state: EvidenceDialogState) => void;
  peopleDiscoveryState: PeopleDiscoveryState;
  webPresenceState: WebPresenceState;
}) {
  if (memoState.status !== "ready") {
    return (
      <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <FileText className="mt-0.5 h-5 w-5 text-muted-foreground" />
          <div>
            <h2 className="text-xl font-semibold text-foreground">CDD Summary</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              AI summary is {memoState.status}. The registry summary below remains available for analyst review.
            </p>
          </div>
        </div>
        <div className="mt-5">
          <SummaryFallback dossier={dossier} />
        </div>
      </section>
    );
  }

  const memo = memoState.memo;
  const citationById = buildCitationMap(dossier, memo, peopleDiscoveryState, webPresenceState);
  const executiveOverview = buildExecutiveOverviewSegments(dossier, memo, citationById, peopleDiscoveryState, webPresenceState);
  const confidenceBlockers = buildConfidenceBlockers(dossier, memo);
  const analystFollowUps = getAnalystFollowUps(dossier);

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex min-w-0 flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">CDD report draft</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-normal text-foreground">Cited executive summary</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Every finding links back to a source reference. Use this as an analyst-review report draft, not a pass/fail opinion.
          </p>
        </div>
        <span className="w-fit rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">
          {memo.provider} / {memo.model}
        </span>
      </div>

      <article className="mt-5 rounded-md border border-border bg-background p-4">
        <p className="text-sm font-semibold text-muted-foreground">Executive overview</p>
        <p className="mt-2 break-words text-base leading-7 text-foreground">
          <EvidenceLinkedText onOpenEvidence={onOpenEvidence} segments={executiveOverview} />
        </p>
      </article>

      <div className="mt-4 grid gap-4">
        {memo.evidenceMemo.length === 0 ? (
          <p className="rounded-md border border-border bg-muted/35 p-4 text-sm text-muted-foreground">
            No cited memo findings were returned.
          </p>
        ) : (
          memo.evidenceMemo.map((item, index) => (
            <article className="rounded-md border border-border bg-background p-4" key={`${item.text}-${index}`}>
              <p className="text-sm font-semibold text-muted-foreground">Finding {index + 1}</p>
              <p className="mt-2 break-words text-base leading-7 text-foreground">{item.text}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {item.citationIds.map((id) => {
                  const citation = citationById.get(id);
                  return (
                    <Button
                      className="h-8 rounded-full font-mono text-xs"
                      disabled={citation === undefined}
                      key={id}
                      onClick={() => {
                        if (citation !== undefined) {
                          onOpenEvidence({ citation, kind: "citation" });
                        }
                      }}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      {id}
                    </Button>
                  );
                })}
              </div>
            </article>
          ))
        )}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1fr)]">
        <article className="rounded-md border border-border bg-background p-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">Risk rating: {memo.riskRating.level}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{memo.riskRating.rationale}</p>
            </div>
          </div>
        </article>
        <article className="rounded-md border border-border bg-background p-4">
          <div className="flex items-start gap-3">
            <ListChecks className="mt-0.5 h-5 w-5 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">Prioritized follow-ups</h3>
              <ol className="mt-3 space-y-3 text-sm leading-6 text-muted-foreground">
                {(analystFollowUps.length > 0
                  ? analystFollowUps
                  : memo.decisionAid.nextSteps.map((step, index) => ({
                      action: step,
                      category: "manual_confirmation" as const,
                      evidenceBasis: [],
                      id: `memo-next-step-${index + 1}`,
                      priority: "recommended" as const,
                      reason: "Memo-generated operational follow-up.",
                      whyThisMatters: "The memo identified this as an operational next step.",
                    }))).map((step, index) => {
                  const followUp = findFollowUpAction(step.action, dossier);
                  const openFollowUp = () => {
                    if (followUp !== null) {
                      onOpenEvidence(buildFollowUpDialogState({
                        action: followUp.action,
                        dossier,
                        nextCheck: followUp.nextCheck,
                        step: step.action,
                      }));
                    }
                  };
                  return (
                    <li className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-2" key={step.id}>
                      <span className="flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card text-xs font-semibold text-foreground">
                        {index + 1}
                      </span>
                      <span className="min-w-0 break-words">
                        <span className="font-medium text-foreground">
                          {followUpPriorityLabel(step.priority)} / {followUpCategoryLabel(step.category)}
                        </span>
                        <span className="mt-1 block">
                          {renderLinkedFollowUpText(step.action, followUp?.action ?? null, openFollowUp)}
                        </span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          Evidence gap: {step.reason}
                        </span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          Why this matters: {step.whyThisMatters}
                        </span>
                        {followUp === null ? null : (
                          <span className="mt-1 block text-xs text-muted-foreground">
                            Supported in Dude via{" "}
                            <button
                              className="font-mono text-primary underline underline-offset-4"
                              onClick={openFollowUp}
                              type="button"
                            >
                              {followUp.action.tool}
                            </button>
                            .
                          </span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </div>
          </div>
        </article>
      </div>

      {confidenceBlockers.length === 0 ? null : (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-4 text-amber-950">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5" />
            <div>
              <h3 className="text-sm font-semibold">What is missing or limiting confidence</h3>
              <ol className="mt-3 space-y-3 text-sm leading-6">
                {confidenceBlockers.map((blocker, index) => (
                  <li
                    className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-2"
                    key={`${blocker.label}-${blocker.detail}`}
                  >
                    <span className="flex h-6 w-6 items-center justify-center rounded-full border border-amber-300 bg-white/70 text-xs font-semibold">
                      {index + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="block break-words font-medium">
                        {blocker.label} <span className="font-normal text-amber-800">({blocker.source})</span>
                      </span>
                      <span className="mt-0.5 block break-words text-amber-900">{blocker.detail}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function ReportBuilder({
  dossier,
  memoState,
  onExportReport,
  peopleDiscoveryState,
  webPresenceState,
}: {
  dossier: BusinessDossier;
  memoState: AnalystMemoState;
  onExportReport: (template: ReportTemplate, format: ReportExportFormat) => void;
  peopleDiscoveryState: PeopleDiscoveryState;
  webPresenceState: WebPresenceState;
}) {
  const [template, setTemplate] = useState<ReportTemplate>(DEFAULT_REPORT_TEMPLATE);

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex min-w-0 flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Report Builder</p>
          <h2 className="mt-1 text-xl font-semibold text-foreground">Choose report pages and writing style</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Build the review artifact from the same cited dossier evidence, reviewer metadata, readiness warnings, and export manifest.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => onExportReport(template, "pdf")} type="button">
            <FileDown className="mr-2 h-4 w-4" />
            Export PDF
          </Button>
          <Button onClick={() => onExportReport(template, "docx")} type="button" variant="outline">
            <FileText className="mr-2 h-4 w-4" />
            Export DOCX
          </Button>
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="space-y-4">
          <div className="rounded-md border border-border bg-background p-4">
            <h3 className="text-sm font-semibold text-foreground">Section presets</h3>
            <div className="mt-3 grid gap-2">
              {REPORT_SECTION_PRESETS.map((preset) => (
                <button
                  className={cn(
                    "rounded-md border border-border p-3 text-left text-sm transition hover:bg-muted",
                    template.id === preset.id ? "bg-muted text-foreground" : "bg-card text-muted-foreground",
                  )}
                  key={preset.id}
                  onClick={() => setTemplate((current) => applyReportSectionPreset(current, preset.id))}
                  type="button"
                >
                  <span className="block font-semibold text-foreground">{preset.name}</span>
                  <span className="mt-1 block text-xs leading-5">{preset.description}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="block rounded-md border border-border bg-background p-4">
            <span className="text-sm font-semibold text-foreground">Writing preset</span>
            <select
              aria-label="Report writing style"
              className="mt-3 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              onChange={(event) => setTemplate((current) => ({
                ...current,
                writingStyle: event.target.value as ReportWritingStyle,
              }))}
              value={template.writingStyle}
            >
              {writingStyles.map((style) => (
                <option key={style} value={style}>{REPORT_WRITING_STYLE_LABELS[style]}</option>
              ))}
            </select>
            <span className="mt-2 block text-sm leading-6 text-muted-foreground">
              {REPORT_WRITING_STYLE_DESCRIPTIONS[template.writingStyle]}
            </span>
          </label>

          <div className="rounded-md border border-border bg-background p-4">
            <h3 className="text-sm font-semibold text-foreground">Reviewer metadata</h3>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Metadata appears in the report front matter and export manifest. Empty fields are shown as not provided.
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {[
                ["preparedBy", "Prepared by"],
                ["reviewedBy", "Reviewed by"],
                ["reviewDate", "Review date"],
                ["caseStatus", "Case status"],
                ["internalReference", "Internal reference"],
                ["reportPurpose", "Report purpose"],
              ].map(([field, label]) => (
                <label className="block text-xs font-medium text-muted-foreground" key={field}>
                  {label}
                  <input
                    className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
                    onChange={(event) => setTemplate((current) =>
                      updateReportReviewerMetadata(current, { [field]: event.target.value }),
                    )}
                    type={field === "reviewDate" ? "date" : "text"}
                    value={template.metadata[field as keyof typeof template.metadata]}
                  />
                </label>
              ))}
            </div>
          </div>

          <ReportPreview
            dossier={dossier}
            memoState={memoState}
            peopleDiscoveryState={peopleDiscoveryState}
            template={template}
            webPresenceState={webPresenceState}
          />
        </div>

        <div className="rounded-md border border-border bg-background p-4">
          <h3 className="text-sm font-semibold text-foreground">Sections</h3>
          <div className="mt-3 grid gap-2">
            {DEFAULT_REPORT_TEMPLATE.sections.map((section) => {
              const selected = template.sections.includes(section);
              const index = template.sections.indexOf(section);
              return (
                <div
                  className={cn(
                    "grid gap-3 rounded-md border p-3 sm:grid-cols-[minmax(0,1fr)_auto]",
                    selected ? "border-border bg-card" : "border-border/70 bg-muted/40 text-muted-foreground",
                  )}
                  key={section}
                >
                  <label className="flex min-w-0 items-start gap-3">
                    <input
                      checked={selected}
                      className="mt-1"
                      disabled={section === "executive_summary"}
                      onChange={() => setTemplate((current) => ({
                        ...current,
                        sections: toggleReportSection(current.sections, section),
                      }))}
                      type="checkbox"
                    />
                    <span>
                      <span className="block text-sm font-semibold">{REPORT_SECTION_LABELS[section]}</span>
                      <span className="mt-1 block text-xs leading-5">{REPORT_SECTION_DESCRIPTIONS[section]}</span>
                    </span>
                  </label>
                  <div className="flex gap-1">
                    <Button
                      aria-label={`Move ${REPORT_SECTION_LABELS[section]} up`}
                      className="h-8 w-8"
                      disabled={!selected || index <= 0}
                      onClick={() => setTemplate((current) => ({
                        ...current,
                        sections: moveReportSection(current.sections, section, "up"),
                      }))}
                      size="icon"
                      type="button"
                      variant="ghost"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      aria-label={`Move ${REPORT_SECTION_LABELS[section]} down`}
                      className="h-8 w-8"
                      disabled={!selected || index === -1 || index >= template.sections.length - 1}
                      onClick={() => setTemplate((current) => ({
                        ...current,
                        sections: moveReportSection(current.sections, section, "down"),
                      }))}
                      size="icon"
                      type="button"
                      variant="ghost"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function EvidencePackTab({
  dossier,
  evidenceStats,
  isPdpaExporting,
  memoState,
  onExportPdpaReport,
  onModuleFollowUp,
  onOpenEvidence,
  orchestration,
  peopleDiscoveryState,
  rerunningModule,
  sharedMemoState,
  webPresenceState,
}: {
  dossier: BusinessDossier;
  evidenceStats: EvidenceStats;
  isPdpaExporting: boolean;
  memoState: AnalystMemoState;
  onExportPdpaReport: (reviewedItemIds: readonly string[]) => void;
  onModuleFollowUp: (request: ModuleFollowUpRequest) => void;
  onOpenEvidence: (state: EvidenceDialogState) => void;
  orchestration?: CddOrchestrationTrace;
  peopleDiscoveryState: PeopleDiscoveryState;
  rerunningModule: RunningBusinessModule;
  sharedMemoState: string | null;
  webPresenceState: WebPresenceState;
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex min-w-0 flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 h-5 w-5 text-muted-foreground" />
          <div>
            <h2 className="text-xl font-semibold text-foreground">Evidence Pack</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              These details support the summary and report exports. Supplemental discovery is not official registry evidence.
            </p>
          </div>
        </div>
        <div className="grid w-full max-w-md grid-cols-3 gap-2 text-center text-sm">
          <div className="rounded-md border border-border p-3">
            <p className="text-lg font-semibold">{evidenceStats.records}</p>
            <p className="text-xs text-muted-foreground">records</p>
          </div>
          <div className="rounded-md border border-border p-3">
            <p className="text-lg font-semibold">{evidenceStats.provenance}</p>
            <p className="text-xs text-muted-foreground">sources</p>
          </div>
          <div className="rounded-md border border-border p-3">
            <p className="text-lg font-semibold">{evidenceStats.gaps}</p>
            <p className="text-xs text-muted-foreground">gaps</p>
          </div>
        </div>
        <Button
          className="w-fit shrink-0"
          onClick={() => onOpenEvidence({
            description: "Scroll this evidence pack for raw rows, source attribution, gaps, and follow-up actions.",
            kind: "pack",
            title: "Evidence pack",
          })}
          type="button"
          variant="outline"
        >
          <SearchCheck className="mr-2 h-4 w-4" />
          How evidence works
        </Button>
      </div>
      <div className="mt-5 space-y-5">
        <OrchestrationTracePanel orchestration={orchestration} />
        <SourceUseWarningsSection
          dossier={dossier}
          peopleDiscovery={peopleDiscoveryState.status === "success" ? peopleDiscoveryState.discovery : undefined}
          webPresence={webPresenceState.status === "success" ? webPresenceState.presence : undefined}
        />
        <SnapshotSection dossier={dossier} />
        <RiskSection dossier={dossier} />
        <ConfidenceSection dossier={dossier} />
        <EvidenceSection dossier={dossier} onModuleFollowUp={onModuleFollowUp} runningModule={rerunningModule} />
        <SupplementalEvidencePanel
          dossier={dossier}
          peopleDiscovery={peopleDiscoveryState.status === "success" ? peopleDiscoveryState.discovery : undefined}
          webPresence={webPresenceState.status === "success" ? webPresenceState.presence : undefined}
        />
        <WebPresenceSection state={webPresenceState} />
        <PeopleDiscoverySection state={peopleDiscoveryState} />
        <PdpaChecklistSection
          dossier={dossier}
          isExporting={isPdpaExporting}
          onExportReport={onExportPdpaReport}
        />
        <NextChecksSection dossier={dossier} />
        <GapsSection dossier={dossier} />
        <ProvenanceSection dossier={dossier} />
        <HandoffSection dossier={dossier} />
        <AnalystMemoSection sharedState={sharedMemoState} state={memoState} />
      </div>
    </section>
  );
}

function EvidenceDialog({
  onRunFollowUp,
  state,
  onOpenChange,
}: {
  onOpenChange: (open: boolean) => void;
  onRunFollowUp: (state: Extract<NonNullable<EvidenceDialogState>, { kind: "followUp" }>) => void;
  state: EvidenceDialogState;
}) {
  return (
    <Dialog open={state !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-3xl overflow-y-auto">
        {state === null ? null : state.kind === "citation" ? (
          <>
            <DialogHeader>
              <DialogTitle>{state.citation.id}</DialogTitle>
              <DialogDescription>{state.citation.source}</DialogDescription>
            </DialogHeader>
            <article className="rounded-md border border-border bg-muted/30 p-4">
              <p className="text-sm font-semibold text-foreground">{state.citation.label}</p>
              <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
                {state.citation.text}
              </p>
            </article>
          </>
        ) : state.kind === "pack" ? (
          <>
            <DialogHeader>
              <DialogTitle>{state.title}</DialogTitle>
              <DialogDescription>{state.description}</DialogDescription>
            </DialogHeader>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{state.title}</DialogTitle>
              <DialogDescription>{state.description}</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="rounded-md border border-border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">Supported Dude tool</p>
                <p className="mt-1 font-mono text-sm text-foreground">{state.tool}</p>
              </div>
              <FollowUpInputView input={state.input} />
              {state.error === undefined ? null : (
                <p className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                  {state.error}
                </p>
              )}
              {state.result === undefined ? null : <FollowUpResultView result={state.result} />}
              <Button
                disabled={state.status === "running"}
                onClick={() => onRunFollowUp(state)}
                type="button"
              >
                {state.status === "running" ? "Running follow-up" : "Run follow-up in Dude"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function DossierFindingsTabs({
  dossier,
  isPdpaExporting,
  memoState,
  onExportPdpaReport,
  onExportReport = () => undefined,
  onModuleFollowUp,
  orchestration,
  peopleDiscoveryState,
  rerunningModule,
  sharedMemoState,
  webPresenceState,
}: DossierFindingsTabsProps) {
  const [evidenceDialog, setEvidenceDialog] = useState<EvidenceDialogState>(null);
  const [activeTab, setActiveTab] = useState<DossierReportTab>("summary");
  const evidenceStats = useMemo(() => buildEvidenceStats(dossier), [dossier]);
  const runFollowUp = async (state: Extract<NonNullable<EvidenceDialogState>, { kind: "followUp" }>) => {
    if (state.moduleRequest !== undefined) {
      setEvidenceDialog({ ...state, status: "running" });
      await onModuleFollowUp(state.moduleRequest);
      setEvidenceDialog({
        ...state,
        result: { message: "Dossier refresh requested. Updated evidence appears on this page when the module call completes." },
        status: "ready",
      });
      return;
    }

    setEvidenceDialog({ ...state, status: "running" });
    try {
      const result = await callTool<unknown>(state.tool, state.input);
      setEvidenceDialog({ ...state, result, status: "ready" });
    } catch (error) {
      setEvidenceDialog({
        ...state,
        error: error instanceof Error ? error.message : "Follow-up failed.",
        status: "error",
      });
    }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-border bg-muted/35 p-1">
        <div className="grid gap-1 sm:grid-cols-3" role="tablist" aria-label="Dossier report views">
          {dossierReportTabs.map((tab) => (
            <button
              aria-selected={activeTab === tab.id}
              className={cn(
                "rounded-md px-4 py-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring",
                activeTab === tab.id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:bg-background/60",
              )}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              role="tab"
              type="button"
            >
              <span className="block text-sm font-semibold">{tab.label}</span>
              <span className="mt-1 block text-xs leading-5">{tab.description}</span>
            </button>
          ))}
        </div>
      </div>

      {activeTab === "summary" ? (
        <CitedSummary
          dossier={dossier}
          memoState={memoState}
          onOpenEvidence={setEvidenceDialog}
          peopleDiscoveryState={peopleDiscoveryState}
          webPresenceState={webPresenceState}
        />
      ) : activeTab === "evidence" ? (
        <EvidencePackTab
          dossier={dossier}
          evidenceStats={evidenceStats}
          isPdpaExporting={isPdpaExporting}
          memoState={memoState}
          onExportPdpaReport={onExportPdpaReport}
          onModuleFollowUp={onModuleFollowUp}
          onOpenEvidence={setEvidenceDialog}
          orchestration={orchestration}
          peopleDiscoveryState={peopleDiscoveryState}
          rerunningModule={rerunningModule}
          sharedMemoState={sharedMemoState}
          webPresenceState={webPresenceState}
        />
      ) : (
        <ReportBuilder
          dossier={dossier}
          memoState={memoState}
          onExportReport={onExportReport}
          peopleDiscoveryState={peopleDiscoveryState}
          webPresenceState={webPresenceState}
        />
      )}

      <EvidenceDialog
        onOpenChange={(open) => {
          if (!open) setEvidenceDialog(null);
        }}
        onRunFollowUp={(state) => {
          void runFollowUp(state);
        }}
        state={evidenceDialog}
      />
    </div>
  );
}
