import {
  ClipboardCheck,
  Database,
  FileSearch,
  LayoutDashboard,
} from "lucide-react";
import { useMemo, type ComponentType } from "react";

import { AnalystMemoSection, type AnalystMemoState } from "@/components/dossier/AnalystMemoSection";
import { ConfidenceSection } from "@/components/dossier/ConfidenceSection";
import { EvidenceSection, type ModuleFollowUpRequest } from "@/components/dossier/EvidenceSection";
import { GapsSection } from "@/components/dossier/GapsSection";
import { HandoffSection } from "@/components/dossier/HandoffSection";
import { NextChecksSection } from "@/components/dossier/NextChecksSection";
import { PdpaChecklistSection } from "@/components/dossier/PdpaChecklistSection";
import { PeopleDiscoverySection, type PeopleDiscoveryState } from "@/components/dossier/PeopleDiscoverySection";
import { ProvenanceSection } from "@/components/dossier/ProvenanceSection";
import { RiskSection } from "@/components/dossier/RiskSection";
import { SnapshotSection } from "@/components/dossier/SnapshotSection";
import { WebPresenceSection, type WebPresenceState } from "@/components/dossier/WebPresenceSection";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { buildPdpaChecklist } from "@/lib/pdpa";
import type { BusinessDossier, BusinessDossierModule } from "@/types/dossier";

type DossierFindingsTabsProps = {
  dossier: BusinessDossier;
  isPdpaExporting: boolean;
  memoState: AnalystMemoState;
  onExportPdpaReport: (reviewedItemIds: readonly string[]) => void;
  onModuleFollowUp: (request: ModuleFollowUpRequest) => void;
  peopleDiscoveryState: PeopleDiscoveryState;
  rerunningModule: BusinessDossierModule | null;
  sharedMemoState: string | null;
  webPresenceState: WebPresenceState;
};

type FindingsTab = {
  count: number;
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
};

function tabCountLabel(count: number): string {
  return count > 99 ? "99+" : String(count);
}

function SummarySection({ dossier }: { dossier: BusinessDossier }) {
  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-6">
      <h2 className="text-base font-semibold text-foreground">Summary</h2>
      <dl className="mt-4 grid gap-3 sm:grid-cols-[repeat(2,minmax(0,1fr))]">
        {dossier.summary.map((item) => (
          <div key={`${item.label}-${item.source ?? ""}`} className="min-w-0 rounded-md border border-border p-3">
            <dt className="text-xs font-medium uppercase text-muted-foreground">{item.label}</dt>
            <dd className="mt-1 break-words text-sm text-foreground">
              {item.value === null || item.value === undefined || item.value === "" ? "-" : String(item.value)}
            </dd>
            {item.source !== undefined && item.source !== null ? (
              <dd className="mt-1 text-xs text-muted-foreground">Source: {item.source}</dd>
            ) : null}
          </div>
        ))}
      </dl>
    </section>
  );
}

const tabTriggerClassName =
  "group min-w-0 flex-1 flex-col gap-1 px-2 py-3 text-xs data-[state=active]:bg-background data-[state=active]:shadow-none";

export function DossierFindingsTabs({
  dossier,
  isPdpaExporting,
  memoState,
  onExportPdpaReport,
  onModuleFollowUp,
  peopleDiscoveryState,
  rerunningModule,
  sharedMemoState,
  webPresenceState,
}: DossierFindingsTabsProps) {
  const pdpaItemCount = useMemo(() => buildPdpaChecklist(dossier).length, [dossier]);
  const searchedModuleCount = dossier.records.resolution?.searchedModules?.length ?? 0;
  const matchedModuleCount = dossier.records.resolution?.matchedModules?.length ?? 0;
  const nextCheckCount = dossier.nextChecks?.length ?? 0;
  const auditCount = dossier.gaps.length + dossier.provenance.length + dossier.freshness.length;
  const tabs: FindingsTab[] = [
    {
      count: 5,
      icon: LayoutDashboard,
      label: "Overview",
      value: "overview",
    },
    {
      count: Math.max(1, Math.max(matchedModuleCount, searchedModuleCount)),
      icon: Database,
      label: "Evidence",
      value: "evidence",
    },
    {
      count: pdpaItemCount + nextCheckCount,
      icon: ClipboardCheck,
      label: "Actions",
      value: "actions",
    },
    {
      count: auditCount,
      icon: FileSearch,
      label: "Audit",
      value: "audit",
    },
  ];

  return (
    <Tabs className="min-w-0" defaultValue="overview">
      <TabsList className="grid w-full grid-cols-2 gap-1 bg-muted/60 p-1 lg:grid-cols-4">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <TabsTrigger className={tabTriggerClassName} key={tab.value} value={tab.value}>
              <span className="flex min-w-0 items-center gap-2">
                <Icon aria-hidden="true" className="h-4 w-4 shrink-0 transition-opacity group-data-[state=inactive]:opacity-50" />
                <span className="truncate">{tab.label}</span>
              </span>
              <span className="min-w-5 rounded-full bg-background px-1.5 py-0.5 text-[11px] text-muted-foreground transition-opacity group-data-[state=inactive]:opacity-50">
                {tabCountLabel(tab.count)}
              </span>
            </TabsTrigger>
          );
        })}
      </TabsList>

      <TabsContent className="mt-5 space-y-5" value="overview">
        <SummarySection dossier={dossier} />
        <SnapshotSection dossier={dossier} />
        <RiskSection dossier={dossier} />
        <AnalystMemoSection sharedState={sharedMemoState} state={memoState} />
        <ConfidenceSection dossier={dossier} />
      </TabsContent>

      <TabsContent className="mt-5 space-y-5" value="evidence">
        <EvidenceSection dossier={dossier} onModuleFollowUp={onModuleFollowUp} runningModule={rerunningModule} />
        <WebPresenceSection state={webPresenceState} />
        <PeopleDiscoverySection state={peopleDiscoveryState} />
      </TabsContent>

      <TabsContent className="mt-5 space-y-5" value="actions">
        <PdpaChecklistSection
          dossier={dossier}
          isExporting={isPdpaExporting}
          onExportReport={onExportPdpaReport}
        />
        <NextChecksSection dossier={dossier} />
      </TabsContent>

      <TabsContent className="mt-5 space-y-5" value="audit">
        <HandoffSection dossier={dossier} />
        <GapsSection dossier={dossier} />
        <ProvenanceSection dossier={dossier} />
      </TabsContent>
    </Tabs>
  );
}
