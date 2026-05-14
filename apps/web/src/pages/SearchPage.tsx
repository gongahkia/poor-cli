import { DiligenceSearch } from "@/components/search/DiligenceSearch";
import { GatewayStatus } from "@/components/status/GatewayStatus";

export function SearchPage() {
  return (
    <main className="min-h-screen bg-background px-6 py-16">
      <section className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <div className="space-y-3">
          <p className="text-sm font-medium text-muted-foreground">Dude</p>
          <h1 className="text-4xl font-semibold tracking-normal text-foreground sm:text-5xl">
            Singapore due diligence in 30 seconds
          </h1>
        </div>

        <DiligenceSearch />

        <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <h2 className="text-base font-semibold text-foreground">How this works</h2>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
            <li>Paste a Singapore company name or UEN</li>
            <li>We pull from ACRA, BCA, BOA, CEA, HSA, GeBIZ, HLB</li>
            <li>Every fact shows its source and when we last verified it</li>
          </ul>
        </section>

        <GatewayStatus />
      </section>
    </main>
  );
}
