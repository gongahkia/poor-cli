import type { PeopleDiscovery, WebPresence } from "@/lib/api/client";
import type { BusinessDossier } from "@/types/dossier";

export type SourceUseWarning = {
  id: "acra_source_use" | "supplemental_analyst_review" | "provider_credentials_license";
  title: string;
  message: string;
  triggeredBy: string[];
};

type SourceUseWarningParams = {
  dossier: BusinessDossier;
  peopleDiscovery?: PeopleDiscovery;
  webPresence?: WebPresence;
};

const normalize = (value: string): string => value.trim().toLowerCase();

const uniqueSorted = (values: readonly string[]): string[] =>
  Array.from(new Set(values.map((value) => value.trim()).filter(Boolean))).sort((left, right) => left.localeCompare(right));

const hasRecords = (value: unknown): boolean => Array.isArray(value) && value.length > 0;

const hasAcraEvidence = (dossier: BusinessDossier): boolean =>
  hasRecords(dossier.records.acra)
  || dossier.provenance.some((item) => normalize(item.source) === "acra" && item.recordCount > 0)
  || dossier.summary.some((item) => normalize(item.source ?? "") === "acra")
  || dossier.evidence.some((item) => normalize(item.source ?? "") === "acra");

const SUPPLEMENTAL_PATTERNS: { label: string; pattern: RegExp }[] = [
  { label: "OpenSanctions", pattern: /opensanctions|sanctions|watchlist/i },
  { label: "OpenCorporates", pattern: /opencorporates/i },
  { label: "adverse media", pattern: /adverse[-\s_]?media|official public feeds/i },
  { label: "relationship graph", pattern: /relationship[-\s_]?graph|control graph/i },
  { label: "web presence", pattern: /tinyfish|web[-\s_]?presence|web[-\s_]?discovery|official website/i },
  { label: "people discovery", pattern: /people[-\s_]?discovery|people follow-up|candidate people/i },
];

const collectSupplementalTriggers = ({
  dossier,
  peopleDiscovery,
  webPresence,
}: SourceUseWarningParams): string[] => {
  const signals = [
    ...(dossier.sourceCoverage ?? []).flatMap((item) => [item.family, item.label, item.status, item.reason, ...item.tools]),
    ...dossier.provenance.flatMap((item) => [item.source, item.tool, item.coverage, item.evidenceType ?? ""]),
    ...dossier.evidence.map((item) => item.source ?? ""),
    ...dossier.freshness.map((item) => item.source),
    ...dossier.gaps.flatMap((gap) => [gap.code, gap.message]),
    ...dossier.limits.flatMap((limit) => [limit.code, limit.message]),
  ];

  const triggers = SUPPLEMENTAL_PATTERNS
    .filter(({ pattern }) => signals.some((signal) => pattern.test(signal)))
    .map(({ label }) => label);

  if (hasRecords(dossier.records.externalDiligence)) {
    triggers.push("external diligence");
  }
  if (webPresence !== undefined && (webPresence.configured || webPresence.results.length > 0 || webPresence.limits.length > 0)) {
    triggers.push("web presence");
  }
  if (peopleDiscovery !== undefined && (peopleDiscovery.configured || peopleDiscovery.results.length > 0 || peopleDiscovery.limits.length > 0)) {
    triggers.push("people discovery");
  }

  return uniqueSorted(triggers);
};

const collectProviderCredentialLicenseTriggers = (dossier: BusinessDossier): string[] => {
  const triggers: string[] = [];

  for (const item of dossier.sourceCoverage ?? []) {
    const credentialBlocked = item.status === "credential_blocked" || (item.requiredCredentials?.length ?? 0) > 0;
    const licenceText = `${item.label} ${item.reason} ${item.tools.join(" ")}`;
    if (credentialBlocked || /licen[cs]e|token|api[_\s-]?key|credential|commercial|provider/i.test(licenceText)) {
      triggers.push(item.label);
    }
  }

  for (const item of dossier.provenance) {
    const text = `${item.source} ${item.tool} ${item.coverage}`;
    if (item.authRequired || /opensanctions|opencorporates|token|api[_\s-]?key|licen[cs]e|commercial/i.test(text)) {
      triggers.push(item.source);
    }
  }

  for (const limit of dossier.limits) {
    if (/licen[cs]e|token|api[_\s-]?key|credential|commercial|provider/i.test(`${limit.code} ${limit.message}`)) {
      triggers.push(limit.code);
    }
  }

  return uniqueSorted(triggers);
};

export function buildSourceUseWarnings(params: SourceUseWarningParams): SourceUseWarning[] {
  const warnings: SourceUseWarning[] = [];

  if (hasAcraEvidence(params.dossier)) {
    warnings.push({
      id: "acra_source_use",
      title: "ACRA source-use review required",
      message: "ACRA-derived company evidence is included for source-attributed CDD analyst review. Do not widen hosted paid redistribution or commercial enrichment workflows until ACRA source-use rights are documented.",
      triggeredBy: ["ACRA"],
    });
  }

  const supplementalTriggers = collectSupplementalTriggers(params);
  if (supplementalTriggers.length > 0) {
    warnings.push({
      id: "supplemental_analyst_review",
      title: "Supplemental evidence is analyst-review only",
      message: `${supplementalTriggers.join(", ")} outputs are supplemental analyst-review signals. They are not official registry facts, sanctions clearance, adverse-media clearance, or ownership/control determinations.`,
      triggeredBy: supplementalTriggers,
    });
  }

  const providerTriggers = collectProviderCredentialLicenseTriggers(params.dossier);
  if (providerTriggers.length > 0) {
    warnings.push({
      id: "provider_credentials_license",
      title: "Provider credentials and licences may constrain coverage",
      message: "Supplemental providers can require API credentials, paid plans, licence review, or usage-specific permissions. Missing credentials, rate limits, or plan limits are coverage blockers and should be documented before export or redistribution.",
      triggeredBy: providerTriggers,
    });
  }

  return warnings;
}

export function buildSourceUseWarningsFromSources(sources: readonly string[]): SourceUseWarning[] {
  const sourceText = sources.join(" ");
  const dossier = {
    evidence: sources.map((source) => ({ label: source, source, value: source })),
    freshness: sources.map((source) => ({ observedAt: "", source })),
    gaps: [],
    limits: [],
    provenance: sources.map((source) => ({
      authRequired: false,
      coverage: source,
      recordCount: 1,
      source,
      tool: source,
    })),
    records: sourceText.match(/\bacra\b/i) === null ? {} : { acra: [{}] },
    summary: [],
    title: "Source warnings",
  } satisfies BusinessDossier;
  return buildSourceUseWarnings({ dossier });
}

export function formatSourceUseWarnings(warnings: readonly SourceUseWarning[]): string {
  return warnings.map((warning) => `${warning.title}: ${warning.message}`).join(" ");
}
