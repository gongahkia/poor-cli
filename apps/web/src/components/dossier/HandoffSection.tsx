import { useMemo, useState } from "react";
import { Check, ChevronDown, ChevronRight, ClipboardCopy } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  BUSINESS_MODULE_LABELS,
  formatLabel,
  formatTimestamp,
  getSummaryString,
} from "@/lib/dossier";
import { followUpCategoryLabel, followUpPriorityLabel, getAnalystFollowUps } from "@/lib/next-checks";
import type { BusinessDossier, BusinessDossierModule } from "@/types/dossier";

const EMPTY_VALUE = "None returned.";

type HandoffRow = {
  label: string;
  value: string;
};

type HandoffSectionGroup = {
  title: string;
  rows: HandoffRow[];
};

const moduleLabel = (module: BusinessDossierModule | string): string =>
  module in BUSINESS_MODULE_LABELS
    ? BUSINESS_MODULE_LABELS[module as BusinessDossierModule]
    : formatLabel(module);

const readableLabel = (value: string): string =>
  formatLabel(value.toLowerCase())
    .replace(/\bAcra\b/g, "ACRA")
    .replace(/\bApi\b/g, "API")
    .replace(/\bSg\b/g, "SG")
    .replace(/\bUen\b/g, "UEN")
    .replace(/\bOpensanctions\b/g, "OpenSanctions");

const joinModules = (modules: BusinessDossierModule[] | undefined): string =>
  modules === undefined || modules.length === 0
    ? "none"
    : modules.map(moduleLabel).join(", ");

const joinLines = (lines: string[]): string =>
  lines.length === 0 ? EMPTY_VALUE : lines.join("\n");

function buildHandoffGroups(dossier: BusinessDossier): HandoffSectionGroup[] {
  const resolution = dossier.records.resolution;
  const entity = getSummaryString(dossier, "Entity");
  const uen = getSummaryString(dossier, "UEN");
  const requestedInput = resolution?.requestedUen
    ?? resolution?.requestedEntityName
    ?? uen
    ?? entity
    ?? dossier.title;

  return [
    {
      title: "Context",
      rows: [
        { label: "Entity input", value: requestedInput },
        { label: "Entity", value: entity ?? "-" },
        { label: "UEN", value: uen ?? "-" },
      ],
    },
    {
      title: "Module coverage",
      rows: [
        { label: "Selected", value: joinModules(resolution?.selectedModules) },
        { label: "Searched", value: joinModules(resolution?.searchedModules) },
        { label: "Matched", value: joinModules(resolution?.matchedModules) },
        { label: "Skipped or not searched", value: joinModules(resolution?.unsearchedModules) },
      ],
    },
    {
      title: "Risk flags",
      rows: [{
        label: "Review",
        value: joinLines(dossier.riskFlags?.map((flag) =>
          `${formatLabel(flag.severity)}: ${flag.message} (${flag.source})`,
        ) ?? []),
      }],
    },
    {
      title: "Prioritized analyst follow-ups",
      rows: [{
        label: "Follow-ups",
        value: joinLines(getAnalystFollowUps(dossier).map((followUp) =>
          `${followUpPriorityLabel(followUp.priority)} / ${followUpCategoryLabel(followUp.category)}: ${followUp.action}\nEvidence gap: ${followUp.reason}\nWhy this matters: ${followUp.whyThisMatters}`,
        )),
      }],
    },
    {
      title: "Freshness and gaps",
      rows: [
        {
          label: "Freshness",
          value: joinLines(dossier.freshness.map((item) =>
            `${item.source}: ${formatTimestamp(item.observedAt) ?? item.observedAt}`,
          )),
        },
        {
          label: "Gaps",
          value: joinLines(dossier.gaps.map((gap) => `${readableLabel(gap.code)}: ${gap.message}`)),
        },
      ],
    },
  ];
}

function buildCopyText(dossier: BusinessDossier, groups: HandoffSectionGroup[]): string {
  const backendMarkdown = dossier.records.handoff?.["markdown"];
  if (typeof backendMarkdown === "string" && backendMarkdown.trim() !== "") {
    return backendMarkdown.trim();
  }

  return [
    "# Agent handoff",
    "",
    ...groups.flatMap((group) => [
      `## ${group.title}`,
      ...group.rows.map((row) => `- ${row.label}: ${row.value.replace(/\n/g, "\n  ")}`),
      "",
    ]),
  ].join("\n").trim();
}

export function HandoffSection({ dossier }: { dossier: BusinessDossier }) {
  const [expanded, setExpanded] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const groups = useMemo(() => buildHandoffGroups(dossier), [dossier]);
  const copyText = useMemo(() => buildCopyText(dossier, groups), [dossier, groups]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(copyText);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("error");
      window.setTimeout(() => setCopyState("idle"), 2000);
    }
  };

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          aria-expanded={expanded}
          className="group flex min-w-0 items-start gap-3 text-left"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          <span className="mt-1 rounded-full bg-muted p-1 text-muted-foreground transition-colors group-hover:text-foreground">
            {expanded ? (
              <ChevronDown aria-hidden="true" className="h-4 w-4" />
            ) : (
              <ChevronRight aria-hidden="true" className="h-4 w-4" />
            )}
          </span>
          <span className="min-w-0">
            <span className="block text-xl font-semibold tracking-normal text-foreground">Agent handoff</span>
            <span className="mt-1 block text-sm leading-6 text-muted-foreground">
              Copy a structured summary for another analyst or agent.
            </span>
          </span>
        </button>
        <Button className="w-fit gap-2" onClick={() => void handleCopy()} type="button" variant="outline">
          {copyState === "copied" ? (
            <Check aria-hidden="true" className="h-4 w-4" />
          ) : (
            <ClipboardCopy aria-hidden="true" className="h-4 w-4" />
          )}
          {copyState === "copied" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy handoff"}
        </Button>
      </div>

      {expanded ? (
        <div className="mt-5 grid gap-3">
          {groups.map((group) => (
            <article className="min-w-0 rounded-md border border-border bg-background p-3" key={group.title}>
              <h3 className="text-sm font-semibold text-foreground">{group.title}</h3>
              <dl className="mt-3 grid gap-3 sm:grid-cols-[13rem_minmax(0,1fr)]">
                {group.rows.map((row) => (
                  <div className="contents" key={`${group.title}-${row.label}`}>
                    <dt className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{row.label}</dt>
                    <dd className="min-w-0 whitespace-pre-line break-words text-sm leading-6 text-foreground">
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
