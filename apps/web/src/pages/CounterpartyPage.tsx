import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfidenceSection } from "@/components/dossier/ConfidenceSection";
import { EvidenceSection } from "@/components/dossier/EvidenceSection";
import { GapsSection } from "@/components/dossier/GapsSection";
import { LimitsSection } from "@/components/dossier/LimitsSection";
import { NextChecksSection } from "@/components/dossier/NextChecksSection";
import { ProvenanceSection } from "@/components/dossier/ProvenanceSection";
import { RiskSection } from "@/components/dossier/RiskSection";
import { SnapshotSection } from "@/components/dossier/SnapshotSection";
import { WebPresenceSection, type WebPresenceState } from "@/components/dossier/WebPresenceSection";
import { GatewayStatus } from "@/components/status/GatewayStatus";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { callTool, getGatewayJson, type WebPresence } from "@/lib/api/client";
import {
  buildBusinessDossierInput,
  buildSummaryLine,
  getSummaryString,
  isNotFoundDossier,
  sanitizeFilenamePart,
  UEN_PATTERN,
} from "@/lib/dossier";
import { exportDossierPdf } from "@/lib/export/pdf";
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
            dossier={state.dossier}
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

function DossierProblem({
  dossier,
  identifier,
  message,
}: {
  dossier?: BusinessDossier;
  identifier: string;
  message: string;
}) {
  return (
    <>
      <div className="rounded-lg border border-border bg-card p-8 shadow-sm">
        <p className="text-sm font-medium text-muted-foreground">Counterparty</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-normal text-foreground">{identifier}</h1>
        <p className="mt-4 text-base leading-7 text-muted-foreground">{message}</p>
        <Button asChild className="mt-6">
          <Link to="/">Try another search</Link>
        </Button>
      </div>
      {dossier === undefined ? null : (
        <>
          <GapsSection dossier={dossier} />
          <ProvenanceSection dossier={dossier} />
          <LimitsSection dossier={dossier} />
        </>
      )}
    </>
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
  const navigate = useNavigate();
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "error">("idle");
  const [webPresenceState, setWebPresenceState] = useState<WebPresenceState>({ status: "loading" });
  const copiedTimer = useRef<number | null>(null);
  const canonicalUen = getSummaryString(dossier, "UEN");
  const entityName = getSummaryString(dossier, "Entity");
  const webPresenceQuery = [entityName, canonicalUen].filter(Boolean).join(" ");

  useEffect(() => {
    return () => {
      if (copiedTimer.current !== null) {
        window.clearTimeout(copiedTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    if (
      canonicalUen !== null
      && UEN_PATTERN.test(canonicalUen)
      && canonicalUen.toUpperCase() !== identifier.trim().toUpperCase()
    ) {
      navigate(`/c/${encodeURIComponent(canonicalUen)}`, { replace: true });
    }
  }, [canonicalUen, identifier, navigate]);

  useEffect(() => {
    const controller = new AbortController();
    if (webPresenceQuery === "") {
      setWebPresenceState({ status: "error", message: "No entity name or UEN was available for web discovery." });
      return () => controller.abort();
    }

    setWebPresenceState({ status: "loading" });
    void getGatewayJson<WebPresence>(
      "/api/v1/dude/web-presence",
      { query: webPresenceQuery },
      { signal: controller.signal },
    )
      .then((presence) => {
        if (!controller.signal.aborted) {
          setWebPresenceState({ status: "success", presence });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setWebPresenceState({
            status: "error",
            message: error instanceof Error ? error.message : "Web discovery is temporarily unavailable.",
          });
        }
      });

    return () => controller.abort();
  }, [webPresenceQuery]);

  const handleExportPdf = async () => {
    setIsExporting(true);
    setExportError(null);
    try {
      const today = new Date().toISOString().slice(0, 10);
      await exportDossierPdf(dossier, {
        filename: `dude-diligence-${sanitizeFilenamePart(identifier)}-${today}.pdf`,
        webPresence: webPresenceState.status === "success" ? webPresenceState.presence : undefined,
      });
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "PDF export failed.");
    } finally {
      setIsExporting(false);
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopyStatus("copied");
      if (copiedTimer.current !== null) {
        window.clearTimeout(copiedTimer.current);
      }
      copiedTimer.current = window.setTimeout(() => setCopyStatus("idle"), 2000);
    } catch {
      setCopyStatus("error");
    }
  };

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
          {resolution?.searchedModules !== undefined ? (
            <span className="rounded-md bg-muted px-2.5 py-1">
              Searched: {resolution.searchedModules.join(", ") || "none"}
            </span>
          ) : resolution?.selectedModules !== undefined ? (
            <span className="rounded-md bg-muted px-2.5 py-1">
              Selected: {resolution.selectedModules.join(", ")}
            </span>
          ) : null}
          {resolution?.unsearchedModules !== undefined && resolution.unsearchedModules.length > 0 ? (
            <span className="rounded-md bg-muted px-2.5 py-1">
              Not searched: {resolution.unsearchedModules.join(", ")}
            </span>
          ) : null}
          {resolution?.matchedModules !== undefined ? (
            <span className="rounded-md bg-muted px-2.5 py-1">
              Matched: {resolution.matchedModules.join(", ") || "none"}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={isExporting} onClick={handleExportPdf} type="button">
            {isExporting ? "Exporting" : "Export PDF"}
          </Button>
          <Button onClick={handleCopyLink} type="button" variant="outline">
            Copy link
          </Button>
          {copyStatus === "copied" ? (
            <p className="text-sm text-muted-foreground">Copied</p>
          ) : copyStatus === "error" ? (
            <p className="text-sm text-destructive">Copy failed</p>
          ) : null}
          {exportError !== null ? (
            <p className="text-sm text-destructive">{exportError}</p>
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

      <SnapshotSection dossier={dossier} />
      <RiskSection dossier={dossier} />
      <ConfidenceSection dossier={dossier} />
      <EvidenceSection dossier={dossier} />
      <WebPresenceSection state={webPresenceState} />
      <NextChecksSection dossier={dossier} />
      <GapsSection dossier={dossier} />
      <ProvenanceSection dossier={dossier} />
      <LimitsSection dossier={dossier} />
      <GatewayStatus />
    </>
  );
}
