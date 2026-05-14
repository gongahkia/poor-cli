import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { EvidenceSection } from "@/components/dossier/EvidenceSection";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { callTool } from "@/lib/api/client";
import {
  buildBusinessDossierInput,
  buildSummaryLine,
  isNotFoundDossier,
} from "@/lib/dossier";
import type { BusinessDossier } from "@/types/dossier";

type DossierState =
  | { status: "loading" }
  | { status: "success"; dossier: BusinessDossier }
  | { status: "not-found"; dossier: BusinessDossier }
  | { status: "error"; message: string };

export function CounterpartyPage() {
  const { identifier = "" } = useParams<{ identifier: string }>();
  const decodedIdentifier = useMemo(() => identifier.trim(), [identifier]);
  const [state, setState] = useState<DossierState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    if (!decodedIdentifier) {
      setState({ status: "error", message: "No counterparty identifier was provided." });
      return () => controller.abort();
    }

    setState({ status: "loading" });

    void callTool<BusinessDossier>(
      "sg_business_dossier",
      buildBusinessDossierInput(decodedIdentifier),
      { signal: controller.signal },
    )
      .then((dossier) => {
        if (controller.signal.aborted) {
          return;
        }
        setState(isNotFoundDossier(dossier)
          ? { status: "not-found", dossier }
          : { status: "success", dossier });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "The diligence request failed.",
        });
      });

    return () => controller.abort();
  }, [decodedIdentifier]);

  return (
    <main className="min-h-screen bg-background px-6 py-12">
      <section className="mx-auto w-full max-w-3xl space-y-6">
        {state.status === "loading" ? (
          <DossierLoading identifier={decodedIdentifier} />
        ) : state.status === "error" ? (
          <DossierProblem
            identifier={decodedIdentifier}
            message={`We couldn't load a Singapore diligence brief for ${decodedIdentifier}. ${state.message}`}
          />
        ) : state.status === "not-found" ? (
          <DossierProblem
            identifier={decodedIdentifier}
            message={`We didn't find a Singapore registry record for ${decodedIdentifier}.`}
          />
        ) : (
          <DossierSuccess identifier={decodedIdentifier} dossier={state.dossier} />
        )}
      </section>
    </main>
  );
}

function DossierLoading({ identifier }: { identifier: string }) {
  return (
    <>
      <div className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">Counterparty</p>
        <h1 className="text-3xl font-semibold tracking-normal text-foreground">Business Dossier</h1>
        <p className="font-mono text-sm text-muted-foreground">{identifier}</p>
      </div>

      <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="space-y-4">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      </div>

      <div className="grid gap-4">
        {[0, 1, 2].map((item) => (
          <div className="rounded-lg border border-border bg-card p-5 shadow-sm" key={item}>
            <Skeleton className="mb-4 h-5 w-28" />
            <Skeleton className="h-20 w-full" />
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <Skeleton className="mb-3 h-4 w-40" />
        <Skeleton className="h-4 w-full" />
      </div>
    </>
  );
}

function DossierProblem({ identifier, message }: { identifier: string; message: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-8 shadow-sm">
      <p className="text-sm font-medium text-muted-foreground">Counterparty</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-normal text-foreground">{identifier}</h1>
      <p className="mt-4 text-base leading-7 text-muted-foreground">{message}</p>
      <Button asChild className="mt-6">
        <Link to="/">Try another search</Link>
      </Button>
    </div>
  );
}

function DossierSuccess({
  dossier,
  identifier,
}: {
  dossier: BusinessDossier;
  identifier: string;
}) {
  const resolution = dossier.records.resolution;

  return (
    <>
      <header className="space-y-4">
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Counterparty</p>
          <h1 className="text-3xl font-semibold tracking-normal text-foreground">{dossier.title}</h1>
          <p className="text-lg leading-8 text-muted-foreground">{buildSummaryLine(dossier)}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
          <span className="rounded-md bg-muted px-2.5 py-1 font-mono text-foreground">{identifier}</span>
          {resolution?.selectedModules !== undefined ? (
            <span className="rounded-md bg-muted px-2.5 py-1">
              Modules selected: {resolution.selectedModules.join(", ")}
            </span>
          ) : null}
          {resolution?.matchedModules !== undefined ? (
            <span className="rounded-md bg-muted px-2.5 py-1">
              Matched: {resolution.matchedModules.join(", ") || "none"}
            </span>
          ) : null}
        </div>
      </header>

      <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <h2 className="text-base font-semibold text-foreground">Summary</h2>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {dossier.summary.map((item) => (
            <div key={`${item.label}-${item.source ?? ""}`} className="rounded-md border border-border p-3">
              <dt className="text-xs font-medium uppercase text-muted-foreground">{item.label}</dt>
              <dd className="mt-1 text-sm text-foreground">
                {item.value === null || item.value === undefined || item.value === "" ? "-" : String(item.value)}
              </dd>
              {item.source !== undefined && item.source !== null ? (
                <dd className="mt-1 text-xs text-muted-foreground">Source: {item.source}</dd>
              ) : null}
            </div>
          ))}
        </dl>
      </section>

      <EvidenceSection dossier={dossier} />
    </>
  );
}
