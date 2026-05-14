import { useParams } from "react-router-dom";

import { Skeleton } from "@/components/ui/skeleton";

export function CounterpartyPage() {
  const { identifier = "" } = useParams<{ identifier: string }>();

  return (
    <main className="min-h-screen bg-background px-6 py-12">
      <section className="mx-auto w-full max-w-3xl space-y-6">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Counterparty</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-normal text-foreground">
            {identifier}
          </h1>
        </div>

        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          {/* Phase 7: call rest-gateway sg_business_dossier here */}
          <div className="space-y-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        </div>
      </section>
    </main>
  );
}
