import { Activity, CircleHelp } from "lucide-react";

import { BulkDiligence } from "@/components/search/BulkDiligence";
import { DiligenceSearch } from "@/components/search/DiligenceSearch";
import { ShortlistPanel } from "@/components/search/ShortlistPanel";
import { GatewayStatus } from "@/components/status/GatewayStatus";
import { Button } from "@/components/ui/button";
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
    <main className="relative min-h-screen bg-background px-6 py-12 sm:py-16">
      <div className="absolute right-4 top-4 flex items-center gap-2 sm:right-6 sm:top-6">
        <SystemStatusDialog />
        <SearchHelpDialog />
      </div>
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_64px] md:items-end">
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

        <DiligenceSearch />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
          <BulkDiligence />
          <ShortlistPanel />
        </div>
      </section>
    </main>
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
            <li>Every result shows searched modules, source provenance, freshness, gaps, and limits</li>
            <li>Use the dossier for analyst review, not legal, tax, credit, or licensed compliance advice</li>
          </ul>
        </section>
      </DialogContent>
    </Dialog>
  );
}
