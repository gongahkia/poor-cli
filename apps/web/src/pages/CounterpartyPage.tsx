import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { AnalystMemoSection, type AnalystMemoState } from "@/components/dossier/AnalystMemoSection";
import { ConfidenceSection } from "@/components/dossier/ConfidenceSection";
import { EvidenceSection, type ModuleFollowUpRequest } from "@/components/dossier/EvidenceSection";
import { GapsSection } from "@/components/dossier/GapsSection";
import { HandoffSection } from "@/components/dossier/HandoffSection";
import { NextChecksSection } from "@/components/dossier/NextChecksSection";
import { ProvenanceSection } from "@/components/dossier/ProvenanceSection";
import { RiskSection } from "@/components/dossier/RiskSection";
import { SnapshotSection } from "@/components/dossier/SnapshotSection";
import { WebPresenceSection, type WebPresenceState } from "@/components/dossier/WebPresenceSection";
import { useToast } from "@/components/notifications/ToastProvider";
import { GatewayStatus } from "@/components/status/GatewayStatus";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { callTool, getGatewayJson, postGatewayJson, type WebPresence } from "@/lib/api/client";
import {
  buildDossierExportSummary,
  exportSingleDossierCsv,
  exportSingleDossierJson,
} from "@/lib/export/structured";
import {
  isShortlisted,
  removeShortlistEntry,
  saveShortlistEntry,
} from "@/lib/shortlist";
import {
  buildBusinessDossierInput,
  buildBusinessDossierFollowUpInput,
  buildSummaryLine,
  getSummaryString,
  isNotFoundDossier,
  sanitizeFilenamePart,
  UEN_PATTERN,
} from "@/lib/dossier";
import { exportDossierPdf } from "@/lib/export/pdf";
import type { AnalystMemoResponse } from "@/types/analyst-memo";
import type { BusinessDossier, BusinessDossierModule } from "@/types/dossier";

type DossierState =
  | { status: "loading" }
  | { status: "success"; dossier: BusinessDossier }
  | { status: "not-found"; dossier: BusinessDossier }
  | { status: "error"; message: string };

export function CounterpartyPage() {
  const { identifier = "" } = useParams<{ identifier: string }>();
  const decodedIdentifier = useMemo(() => identifier.trim(), [identifier]);
  const [state, setState] = useState<DossierState>({ status: "loading" });
  const { notify } = useToast();

  useEffect(() => {
    const controller = new AbortController();

    if (!decodedIdentifier) {
      setState({ status: "error", message: "No counterparty identifier was provided." });
      notify({ title: "Dossier request missing identifier", tone: "error" });
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
        notify({
          title: "Dossier request failed",
          description: error instanceof Error ? error.message : "The diligence request failed.",
          tone: "error",
        });
      });

    return () => controller.abort();
  }, [decodedIdentifier, notify]);

  return (
    <main className="min-h-screen overflow-x-hidden bg-background px-4 py-8 sm:px-6 sm:py-12">
      <section className="mx-auto w-full max-w-6xl min-w-0 space-y-5">
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
        <h1 className="mt-2 break-words text-3xl font-semibold tracking-normal text-foreground">{identifier}</h1>
        <p className="mt-4 text-base leading-7 text-muted-foreground">{message}</p>
        <Button asChild className="mt-6">
          <Link to="/">Try another search</Link>
        </Button>
      </div>
      {dossier === undefined ? null : (
        <>
          <GapsSection dossier={dossier} />
          <ProvenanceSection dossier={dossier} />
        </>
      )}
    </>
  );
}

function DossierSuccess({
  dossier: initialDossier,
  identifier,
}: {
  dossier: BusinessDossier;
  identifier: string;
}) {
  const [dossier, setDossier] = useState(initialDossier);
  const resolution = dossier.records.resolution;
  const navigate = useNavigate();
  const location = useLocation();
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "error">("idle");
  const [rerunningModule, setRerunningModule] = useState<BusinessDossierModule | null>(null);
  const [webPresenceState, setWebPresenceState] = useState<WebPresenceState>({ status: "loading" });
  const [memoState, setMemoState] = useState<AnalystMemoState>({ status: "loading" });
  const [shortlisted, setShortlisted] = useState(false);
  const { notify } = useToast();
  const copiedTimer = useRef<number | null>(null);
  const sharedMemoState = useMemo(() => new URLSearchParams(location.search).get("memo"), [location.search]);
  const canonicalUen = getSummaryString(dossier, "UEN");
  const entityName = getSummaryString(dossier, "Entity");
  const shortlistIdentifier = canonicalUen ?? entityName ?? identifier;
  const webPresenceQuery = [entityName, canonicalUen].filter(Boolean).join(" ");
  const searchedCount = resolution?.searchedModules?.length ?? 0;
  const matchedCount = resolution?.matchedModules?.length ?? 0;
  const inferredSectorCount = resolution?.inferredSectors?.length ?? 0;
  const coverageLine = resolution === undefined
    ? null
    : `${matchedCount} of ${searchedCount} searched modules returned evidence${inferredSectorCount === 0 ? "" : `; ${inferredSectorCount} sector ${inferredSectorCount === 1 ? "hint was" : "hints were"} inferred from ACRA SSIC`}.`;

  useEffect(() => {
    setDossier(initialDossier);
  }, [initialDossier]);

  useEffect(() => {
    return () => {
      if (copiedTimer.current !== null) {
        window.clearTimeout(copiedTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    setShortlisted(isShortlisted(shortlistIdentifier));
  }, [shortlistIdentifier]);

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

  useEffect(() => {
    const controller = new AbortController();
    if (webPresenceState.status === "loading") {
      setMemoState({ status: "loading" });
      return () => controller.abort();
    }

    setMemoState({ status: "loading" });
    const webPresence = webPresenceState.status === "success" ? webPresenceState.presence : undefined;
    void postGatewayJson<AnalystMemoResponse>(
      "/api/v1/dude/memo",
      {
        dossier,
        ...(webPresence === undefined ? {} : { webPresence }),
      },
      { signal: controller.signal },
    )
      .then((memo) => {
        if (controller.signal.aborted) {
          return;
        }
        if (memo.status === "ready") {
          setMemoState({ status: "ready", memo });
        } else if (memo.status === "unavailable") {
          setMemoState({ status: "unavailable", memo });
        } else {
          setMemoState({ status: "error", message: memo.reason.message, memo });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMemoState({
            status: "error",
            message: error instanceof Error ? error.message : "Analyst memo request failed.",
          });
        }
      });

    return () => controller.abort();
  }, [dossier, webPresenceState]);

  useEffect(() => {
    const nextMemoState = memoState.status === "loading" ? "pending" : memoState.status;
    const params = new URLSearchParams(location.search);
    if (params.get("memo") === nextMemoState) {
      return;
    }
    params.set("memo", nextMemoState);
    navigate({
      pathname: location.pathname,
      search: `?${params.toString()}`,
    }, { replace: true });
  }, [location.pathname, location.search, memoState.status, navigate]);

  const handleExportPdf = async () => {
    setIsExporting(true);
    setExportError(null);
    try {
      const today = new Date().toISOString().slice(0, 10);
      await exportDossierPdf(dossier, {
        filename: `dude-diligence-${sanitizeFilenamePart(identifier)}-${today}.pdf`,
        ...(memoState.status === "ready" ? { analystMemo: memoState.memo } : {}),
        ...(webPresenceState.status === "success" ? { webPresence: webPresenceState.presence } : {}),
      });
      notify({ title: "PDF export started", description: dossier.title, tone: "success" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "PDF export failed.";
      setExportError(message);
      notify({ title: "PDF export failed", description: message, tone: "error" });
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportCsv = async () => {
    try {
      await exportSingleDossierCsv(dossier);
      notify({ title: "CSV export started", description: dossier.title, tone: "success" });
    } catch (error) {
      notify({
        title: "CSV export failed",
        description: error instanceof Error ? error.message : "Unable to export CSV.",
        tone: "error",
      });
    }
  };

  const handleExportJson = async () => {
    try {
      await exportSingleDossierJson({
        dossier,
        ...(memoState.status === "ready" ? { analystMemo: memoState.memo } : {}),
        ...(webPresenceState.status === "success" ? { webPresence: webPresenceState.presence } : {}),
      });
      notify({ title: "JSON export started", description: dossier.title, tone: "success" });
    } catch (error) {
      notify({
        title: "JSON export failed",
        description: error instanceof Error ? error.message : "Unable to export JSON.",
        tone: "error",
      });
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopyStatus("copied");
      notify({ title: "Link copied", description: "Dossier URL copied to clipboard.", tone: "success" });
      if (copiedTimer.current !== null) {
        window.clearTimeout(copiedTimer.current);
      }
      copiedTimer.current = window.setTimeout(() => setCopyStatus("idle"), 2000);
    } catch {
      setCopyStatus("error");
      notify({ title: "Copy failed", description: "The browser could not copy the dossier URL.", tone: "error" });
    }
  };

  const handleToggleShortlist = () => {
    if (shortlisted) {
      removeShortlistEntry(shortlistIdentifier);
      setShortlisted(false);
      notify({ title: "Removed saved dossier", description: shortlistIdentifier, tone: "info" });
      return;
    }
    saveShortlistEntry(buildDossierExportSummary(dossier));
    setShortlisted(true);
    notify({ title: "Saved dossier", description: shortlistIdentifier, tone: "success" });
  };

  const handleModuleFollowUp = async (request: ModuleFollowUpRequest) => {
    setRerunningModule(request.module);
    try {
      const followUpInput = buildBusinessDossierFollowUpInput({
        dossier,
        identifier,
        module: request.module,
        value: request.value,
      });
      const nextDossier = await callTool<BusinessDossier>("sg_business_dossier", followUpInput);
      setDossier(nextDossier);
      notify({
        title: `${request.module.toUpperCase()} follow-up complete`,
        description: "Dossier evidence, provenance, freshness, gaps, and limits were refreshed.",
        tone: "success",
      });
    } catch (error) {
      notify({
        title: `${request.module.toUpperCase()} follow-up failed`,
        description: error instanceof Error ? error.message : "Unable to rerun this module.",
        tone: "error",
      });
    } finally {
      setRerunningModule(null);
    }
  };

  return (
    <>
      <header className="space-y-4">
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Counterparty</p>
          <h1 className="break-words text-3xl font-semibold tracking-normal text-foreground">{dossier.title}</h1>
          <p className="text-lg leading-8 text-muted-foreground">{buildSummaryLine(dossier)}</p>
          {coverageLine === null ? null : (
            <p className="text-sm leading-6 text-muted-foreground">
              {coverageLine} Skipped modules were not queried and are not negative evidence.
            </p>
          )}
        </div>
        <div className="flex min-w-0 flex-wrap gap-2 text-sm text-muted-foreground">
          <span className="max-w-full break-all rounded-md bg-muted px-2.5 py-1 font-mono text-foreground">{identifier}</span>
          {resolution?.searchedModules !== undefined ? (
            <span className="max-w-full break-words rounded-md bg-muted px-2.5 py-1">
              Searched: {resolution.searchedModules.join(", ") || "none"}
            </span>
          ) : resolution?.selectedModules !== undefined ? (
            <span className="max-w-full break-words rounded-md bg-muted px-2.5 py-1">
              Selected: {resolution.selectedModules.join(", ")}
            </span>
          ) : null}
          {resolution?.unsearchedModules !== undefined && resolution.unsearchedModules.length > 0 ? (
            <span className="max-w-full break-words rounded-md bg-muted px-2.5 py-1">
              Not searched: {resolution.unsearchedModules.join(", ")}
            </span>
          ) : null}
          {resolution?.matchedModules !== undefined ? (
            <span className="max-w-full break-words rounded-md bg-muted px-2.5 py-1">
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
          <Button
            onClick={() => void handleExportCsv()}
            type="button"
            variant="outline"
          >
            Export CSV
          </Button>
          <Button
            onClick={() => void handleExportJson()}
            type="button"
            variant="outline"
          >
            Export JSON
          </Button>
          <Button onClick={handleToggleShortlist} type="button" variant="outline">
            {shortlisted ? "Remove saved" : "Save"}
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

      <SnapshotSection dossier={dossier} />
      <RiskSection dossier={dossier} />
      <AnalystMemoSection sharedState={sharedMemoState} state={memoState} />
      <ConfidenceSection dossier={dossier} />
      <EvidenceSection dossier={dossier} onModuleFollowUp={handleModuleFollowUp} runningModule={rerunningModule} />
      <WebPresenceSection state={webPresenceState} />
      <NextChecksSection dossier={dossier} />
      <HandoffSection dossier={dossier} />
      <GapsSection dossier={dossier} />
      <ProvenanceSection dossier={dossier} />
      <GatewayStatus />
    </>
  );
}
