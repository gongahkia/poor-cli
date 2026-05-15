import { CircleHelp } from "lucide-react";

import { DiligenceSearch } from "@/components/search/DiligenceSearch";
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
      <div className="absolute right-4 top-4 sm:right-6 sm:top-6">
        <SearchHelpDialog />
      </div>
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_112px] md:items-end">
          <div className="space-y-3">
            <p className="text-sm font-medium text-muted-foreground">Dude</p>
            <h1 className="text-4xl font-semibold tracking-normal text-foreground sm:text-5xl">
              Singapore due diligence in 30 seconds
            </h1>
          </div>
          <div className="flex justify-start md:justify-end">
            <img
              alt="Dude standing"
              className="h-16 w-16 object-contain drop-shadow-sm sm:h-20 sm:w-20 md:h-28 md:w-28"
              decoding="async"
              fetchPriority="high"
              src={DUDE_LANDING_EMOJI_URL}
            />
          </div>
        </div>

        <DiligenceSearch />
      </section>
    </main>
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
          <DialogTitle>Help and status</DialogTitle>
          <DialogDescription>
            Quick reference for searches and the local gateway.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <section>
            <h2 className="text-sm font-semibold text-foreground">How this works</h2>
            <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
              <li>Paste a Singapore company name or UEN</li>
              <li>Default company searches verify identity against ACRA first</li>
              <li>Sector registries run only when selected or inferred from official SSIC evidence</li>
              <li>Every result shows searched modules, source provenance, freshness, gaps, and limits</li>
            </ul>
          </section>
          <section>
            <h2 className="text-sm font-semibold text-foreground">System status</h2>
            <div className="mt-3">
              <GatewayStatus />
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
