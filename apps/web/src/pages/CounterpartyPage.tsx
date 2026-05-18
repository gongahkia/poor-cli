import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { BookmarkCheck, BookmarkPlus, Braces, Copy, FileDown, Loader2, Table2 } from "lucide-react";

import type { AnalystMemoState } from "@/components/dossier/AnalystMemoSection";
import { DossierHeaderLogo } from "@/components/dossier/DossierHeaderLogo";
import { DossierFindingsTabs } from "@/components/dossier/DossierFindingsTabs";
import type { ModuleFollowUpRequest, RunningBusinessModule } from "@/components/dossier/EvidenceSection";
import { GapsSection } from "@/components/dossier/GapsSection";
import type { PeopleDiscoveryState } from "@/components/dossier/PeopleDiscoverySection";
import { ProvenanceSection } from "@/components/dossier/ProvenanceSection";
import type { WebPresenceState } from "@/components/dossier/WebPresenceSection";
import { useToast } from "@/components/notifications/ToastProvider";
import { Button } from "@/components/ui/button";
import { callTool, getGatewayJson, postGatewayJson, type PeopleDiscovery, type WebPresence } from "@/lib/api/client";
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
  buildBusinessDossierExpandedInput,
  buildBusinessDossierFollowUpInput,
  buildSummaryLine,
  getSummaryString,
  isNotFoundDossier,
  sanitizeFilenamePart,
  UEN_PATTERN,
} from "@/lib/dossier";
import { exportDossierPdf } from "@/lib/export/pdf";
import { exportPdpaReportPdf } from "@/lib/export/pdpa";
import { persistAuditEvent, persistDossierRecord } from "@/lib/workspace-store";
import type { AnalystMemoResponse } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";

type DossierState =
  | { status: "loading" }
  | { status: "success"; dossier: BusinessDossier }
  | { status: "not-found"; dossier: BusinessDossier }
  | { status: "error"; message: string };

function DossierActionButton({
  children,
  disabled,
  label,
  onClick,
  variant = "outline",
}: {
  children: ReactNode;
  disabled?: boolean;
  label: string;
  onClick: () => void;
  variant?: "default" | "outline";
}) {
  return (
    <Button
      aria-label={label}
      className="group h-10 w-10 justify-start gap-2 overflow-hidden px-0 transition-[width,padding] duration-200 ease-out hover:w-36 hover:px-3 focus-visible:w-36 focus-visible:px-3"
      disabled={disabled}
      onClick={onClick}
      title={label}
      type="button"
      variant={variant}
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center transition-[height,width] duration-200 group-hover:h-auto group-hover:w-5 group-focus-visible:h-auto group-focus-visible:w-5">
        {children}
      </span>
      <span className="max-w-0 overflow-hidden whitespace-nowrap text-sm opacity-0 transition-[max-width,opacity] duration-200 group-hover:max-w-24 group-hover:opacity-100 group-focus-visible:max-w-24 group-focus-visible:opacity-100">
        {label}
      </span>
    </Button>
  );
}

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
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const isSlow = elapsedSeconds >= 4;

  useEffect(() => {
    const startedAt = Date.now();
    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    return () => window.clearInterval(interval);
  }, []);

  return (
    <>
      <div className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">Counterparty</p>
        <h1 className="text-3xl font-semibold tracking-normal text-foreground">Business Dossier</h1>
        <p className="font-mono text-sm text-muted-foreground">{identifier}</p>
      </div>

      <section className="min-w-0 rounded-lg border border-border bg-card p-5 shadow-sm sm:p-6">
        <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-base font-semibold tracking-normal text-foreground">Loading dossier</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Requesting <span className="font-mono text-foreground">sg_business_dossier</span> from the REST gateway.
              Source-level evidence, skipped modules, freshness, and gaps will appear after this request returns.
            </p>
          </div>
          <span className="w-fit shrink-0 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
            {elapsedSeconds}s
          </span>
        </div>

        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-muted">
          <div className="h-full w-1/3 rounded-full bg-foreground/60 motion-safe:animate-[loading-bar_1.2s_ease-in-out_infinite]" />
        </div>

        {isSlow ? (
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            This is taking longer than usual. The gateway may be waiting on upstream Singapore data sources; no individual
            module step is shown until the dossier response is available.
          </p>
        ) : (
          <p className="mt-4 text-xs leading-5 text-muted-foreground">
            This loading state reflects one live gateway request, not simulated per-module progress.
          </p>
        )}
      </section>
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
  const [isPdpaExporting, setIsPdpaExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "error">("idle");
  const [rerunningModule, setRerunningModule] = useState<RunningBusinessModule>(null);
  const [webPresenceState, setWebPresenceState] = useState<WebPresenceState>({ status: "loading" });
  const [peopleDiscoveryState, setPeopleDiscoveryState] = useState<PeopleDiscoveryState>({ status: "loading" });
  const [memoState, setMemoState] = useState<AnalystMemoState>({ status: "loading" });
  const [shortlisted, setShortlisted] = useState(false);
  const { notify } = useToast();
  const copiedTimer = useRef<number | null>(null);
  const sharedMemoState = useMemo(() => new URLSearchParams(location.search).get("memo"), [location.search]);
  const canonicalUen = getSummaryString(dossier, "UEN");
  const entityName = getSummaryString(dossier, "Entity");
  const shortlistIdentifier = canonicalUen ?? entityName ?? identifier;
  const webPresenceQuery = [entityName, canonicalUen].filter(Boolean).join(" ");

  useEffect(() => {
    setDossier(initialDossier);
  }, [initialDossier]);

  useEffect(() => {
    persistDossierRecord({ identifier, dossier });
    persistAuditEvent({
      eventType: "dossier_generation",
      input: { identifier },
      output: dossier,
      provenance: dossier.provenance,
      freshness: dossier.freshness,
      metadata: {
        matchedModules: dossier.records.resolution?.matchedModules ?? [],
        gapCount: dossier.gaps.length,
      },
    });
  }, [dossier, identifier]);

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
    if (entityName === null) {
      setPeopleDiscoveryState({ status: "error", message: "No entity name was available for people follow-up." });
      return () => controller.abort();
    }

    setPeopleDiscoveryState({ status: "loading" });
    void getGatewayJson<PeopleDiscovery>(
      "/api/v1/dude/people-discovery",
      {
        entityName,
        ...(canonicalUen === null ? {} : { uen: canonicalUen }),
      },
      { signal: controller.signal },
    )
      .then((discovery) => {
        if (!controller.signal.aborted) {
          setPeopleDiscoveryState({ status: "success", discovery });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setPeopleDiscoveryState({
            status: "error",
            message: error instanceof Error ? error.message : "People follow-up is temporarily unavailable.",
          });
        }
      });

    return () => controller.abort();
  }, [canonicalUen, entityName]);

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

  useEffect(() => {
    if (memoState.status === "loading") return;
    persistDossierRecord({
      identifier,
      dossier,
      analystMemo: memoState.status === "ready" || memoState.status === "unavailable" ? memoState.memo : undefined,
      webPresence: webPresenceState.status === "success" ? webPresenceState.presence : undefined,
    });
    persistAuditEvent({
      eventType: "memo_generation",
      input: { identifier, memoState: memoState.status },
      output: memoState,
      provenance: dossier.provenance,
      freshness: dossier.freshness,
      metadata: {
        providerStatus: memoState.status,
        webPresenceStatus: webPresenceState.status,
      },
    });
  }, [dossier, identifier, memoState, webPresenceState]);

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
      persistAuditEvent({
        eventType: "export",
        permission: "export:run",
        input: { identifier, format: "pdf" },
        output: { filename: `dude-diligence-${sanitizeFilenamePart(identifier)}-${today}.pdf` },
        provenance: dossier.provenance,
        freshness: dossier.freshness,
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
      persistAuditEvent({
        eventType: "export",
        permission: "export:run",
        input: { identifier, format: "csv" },
        output: { title: dossier.title },
        provenance: dossier.provenance,
        freshness: dossier.freshness,
      });
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
      persistAuditEvent({
        eventType: "export",
        permission: "export:run",
        input: { identifier, format: "json" },
        output: { title: dossier.title },
        provenance: dossier.provenance,
        freshness: dossier.freshness,
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

  const handleExportPdpaReport = async (reviewedItemIds: readonly string[]) => {
    setIsPdpaExporting(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      await exportPdpaReportPdf(dossier, {
        filename: `dude-pdpa-checklist-${sanitizeFilenamePart(identifier)}-${today}.pdf`,
        reviewedItemIds,
      });
      persistAuditEvent({
        eventType: "export",
        permission: "export:run",
        input: { identifier, format: "pdpa_pdf", reviewedItemIds },
        output: { filename: `dude-pdpa-checklist-${sanitizeFilenamePart(identifier)}-${today}.pdf` },
        provenance: dossier.provenance,
        freshness: dossier.freshness,
      });
      notify({ title: "PDPA report export started", description: dossier.title, tone: "success" });
    } catch (error) {
      notify({
        title: "PDPA report export failed",
        description: error instanceof Error ? error.message : "Unable to export PDPA report.",
        tone: "error",
      });
    } finally {
      setIsPdpaExporting(false);
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
    setRerunningModule(request.kind === "all" ? "all" : request.module);
    try {
      const followUpInput = request.kind === "all"
        ? buildBusinessDossierExpandedInput({
            dossier,
            identifier,
            modules: request.modules,
            value: request.value,
          })
        : buildBusinessDossierFollowUpInput({
            dossier,
            identifier,
            module: request.module,
            value: request.value,
          });
      const nextDossier = await callTool<BusinessDossier>("sg_business_dossier", followUpInput);
      setDossier(nextDossier);
      persistAuditEvent({
        eventType: "search",
        input: followUpInput,
        output: nextDossier,
        provenance: nextDossier.provenance,
        freshness: nextDossier.freshness,
        metadata: { module: request.kind === "all" ? "all" : request.module },
      });
      notify({
        title: request.kind === "all" ? "All module checks complete" : `${request.module.toUpperCase()} follow-up complete`,
        description: "Dossier evidence, provenance, freshness, gaps, and limits were refreshed.",
        tone: "success",
      });
    } catch (error) {
      notify({
        title: request.kind === "all" ? "All module checks failed" : `${request.module.toUpperCase()} follow-up failed`,
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
        <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start">
          <DossierHeaderLogo dossier={dossier} />
          <div className="min-w-0 space-y-2">
            <p className="text-sm font-medium text-muted-foreground">Counterparty</p>
            <h1 className="break-words text-3xl font-semibold tracking-normal text-foreground">{dossier.title}</h1>
            <p className="text-lg leading-8 text-muted-foreground">{buildSummaryLine(dossier)}</p>
          </div>
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
          <DossierActionButton
            disabled={isExporting}
            label={isExporting ? "Exporting PDF" : "Export PDF"}
            onClick={handleExportPdf}
            variant="default"
          >
            {isExporting ? (
              <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin" />
            ) : (
              <FileDown aria-hidden="true" className="h-5 w-5" />
            )}
          </DossierActionButton>
          <DossierActionButton label="Copy link" onClick={handleCopyLink}>
            <Copy aria-hidden="true" className="h-5 w-5" />
          </DossierActionButton>
          <DossierActionButton label="Export CSV" onClick={() => void handleExportCsv()}>
            <Table2 aria-hidden="true" className="h-5 w-5" />
          </DossierActionButton>
          <DossierActionButton label="Export JSON" onClick={() => void handleExportJson()}>
            <Braces aria-hidden="true" className="h-5 w-5" />
          </DossierActionButton>
          <DossierActionButton
            label={shortlisted ? "Remove saved" : "Save dossier"}
            onClick={handleToggleShortlist}
          >
            {shortlisted ? (
              <BookmarkCheck aria-hidden="true" className="h-5 w-5" />
            ) : (
              <BookmarkPlus aria-hidden="true" className="h-5 w-5" />
            )}
          </DossierActionButton>
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

      <DossierFindingsTabs
        dossier={dossier}
        isPdpaExporting={isPdpaExporting}
        memoState={memoState}
        onExportPdpaReport={(reviewedItemIds) => void handleExportPdpaReport(reviewedItemIds)}
        onModuleFollowUp={handleModuleFollowUp}
        peopleDiscoveryState={peopleDiscoveryState}
        rerunningModule={rerunningModule}
        sharedMemoState={sharedMemoState}
        webPresenceState={webPresenceState}
      />
    </>
  );
}
