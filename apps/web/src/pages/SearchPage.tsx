import { Activity, CircleHelp, SlidersHorizontal } from "lucide-react";

import { BackendLogsDialog } from "@/components/debug/BackendLogsDialog";
import { BulkDiligence } from "@/components/search/BulkDiligence";
import { DiligenceSearch } from "@/components/search/DiligenceSearch";
import { ShortlistPanel } from "@/components/search/ShortlistPanel";
import { GatewayStatus } from "@/components/status/GatewayStatus";
import { Button } from "@/components/ui/button";
import { WorkspaceBadge } from "@/components/workspace/WorkspaceBadge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { DUDE_LANDING_EMOJI_URL } from "@/lib/brand/dude";

export function SearchPage() {
  return (
    <main className="relative min-h-dvh bg-background px-6">
      <div className="absolute right-4 top-4 flex items-center gap-2 sm:right-6 sm:top-6">
        <WorkspaceBadge />
        <SystemStatusDialog />
        <BackendLogsDialog />
        <SearchHelpDialog />
      </div>
      <section className="mx-auto grid min-h-dvh w-full max-w-4xl grid-rows-[minmax(0,1fr)_auto_minmax(0,1fr)] py-16">
        <div className="grid items-end gap-6 pb-8 md:grid-cols-[minmax(0,1fr)_64px]">
          <div className="space-y-3">
            <p className="text-sm font-medium text-muted-foreground">Dude</p>
            <h1 className="text-4xl font-semibold tracking-normal text-foreground sm:text-5xl">
              Client CDD onboarding for Singapore teams
            </h1>
          </div>
          <div className="flex justify-start md:justify-end">
            <img
              alt="Dude standing"
              className="h-10 w-10 object-contain drop-shadow-sm sm:h-12 sm:w-12 md:h-16 md:w-16"
              decoding="async"
              fetchPriority="high"
              src={DUDE_LANDING_EMOJI_URL}
            />
          </div>
        </div>

        <div className="w-full">
          <DiligenceSearch secondaryAction={<SearchToolsDialog />} />
        </div>
        <div aria-hidden="true" />
      </section>
    </main>
  );
}

function SearchToolsDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          aria-label="Open bulk checks and shortlist tools"
          className="h-12 gap-2 px-4"
          type="button"
          variant="outline"
        >
          <SlidersHorizontal className="h-4 w-4" />
          <span>Tools</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-5xl overflow-y-auto rounded-[28px] border-border bg-background p-1 shadow-2xl">
        <div className="rounded-[24px] bg-muted/35 p-5 sm:p-6">
          <DialogHeader className="pr-10">
            <DialogTitle>Workspace tools</DialogTitle>
            <DialogDescription>
              Bulk checks and saved counterparties stay available without competing with the primary search.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
            <BulkDiligence />
            <ShortlistPanel />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SystemStatusDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          aria-label="Open system status"
          className="h-9 w-9 rounded-full"
          size="icon"
          type="button"
          variant="outline"
        >
          <Activity className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>System status</DialogTitle>
          <DialogDescription>
            Gateway uptime and service readiness.
          </DialogDescription>
        </DialogHeader>

        <GatewayStatus variant="panel" />
      </DialogContent>
    </Dialog>
  );
}

function SearchHelpDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          aria-label="Open help"
          className="h-9 w-9 rounded-full"
          size="icon"
          type="button"
          variant="outline"
        >
          <CircleHelp className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Help</DialogTitle>
          <DialogDescription>
            Quick reference for client intake searches.
          </DialogDescription>
        </DialogHeader>

        <section>
          <h2 className="text-sm font-semibold text-foreground">How this works</h2>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
            <li>Paste a Singapore client or counterparty company name or UEN</li>
            <li>Default company searches verify identity against ACRA first</li>
            <li>Sector registries run only when selected or inferred from official SSIC evidence</li>
            <li>Every result shows searched modules, source provenance, freshness, and gaps</li>
            <li>Use the dossier for analyst review, not legal, tax, credit, or licensed compliance advice</li>
          </ul>
        </section>
      </DialogContent>
    </Dialog>
  );
}
