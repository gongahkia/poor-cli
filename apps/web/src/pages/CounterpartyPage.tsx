import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import {
  postGatewayJson,
  type CounterpartyResolutionCandidate,
  type CounterpartyResolutionResult,
  type PeopleDiscovery,
  type WebPresence,
} from "@/lib/api/client";
import {
  formatRecordValue,
  getDossierRecordGroups,
  getSummaryString,
  isNotFoundDossier,
  sanitizeFilenamePart,
} from "@/lib/dossier";
import {
  DEFAULT_REPORT_TEMPLATE,
  REPORT_WRITING_STYLE_LABELS,
  type ReportExportFormat,
  type ReportTemplate,
  type ReportWritingStyle,
} from "@/lib/report-template";
import { followUpPriorityLabel, getAnalystFollowUps } from "@/lib/next-checks";
import { resolveActiveSession } from "@/lib/workspace";
import {
  addCddCaseNote,
  addCddCaseTask,
  attachDossierToCddCase,
  buildCddCaseId,
  buildCddCaseJsonPackage,
  getCddCase,
  loadWorkspaceStore,
  recordCddCaseExport,
  saveWorkspaceStore,
  setCddCaseTaskCompleted,
  updateCddCaseStatus,
  upsertCddCase,
  type CddCaseRecord,
  type CddCaseStatus,
} from "@/lib/workspace-store";
import type { AnalystMemoResponse } from "@/types/analyst-memo";
import type {
  BusinessDossier,
  BusinessDossierModuleReason,
  BriefSummaryItem,
  SectorWorkflowGuideItem,
  SourceCoverageItem,
} from "@/types/dossier";
import type { CddOrchestrationTrace } from "@/types/orchestration";

type DossierState =
  | { status: "loading" }
  | { status: "needs-confirmation"; resolution: CounterpartyResolutionResult }
  | { status: "success"; dossier: BusinessDossier; response: CddOrchestratorResponse }
  | { status: "not-found"; dossier: BusinessDossier; response: CddOrchestratorResponse }
  | { status: "error"; message: string };

type CddOrchestratorResponse = {
  dossier: BusinessDossier;
  webPresence: WebPresence;
  peopleDiscovery: PeopleDiscovery;
  memo: AnalystMemoResponse;
  generatedAt: string;
  resolution?: CounterpartyResolutionResult;
  orchestration: CddOrchestrationTrace;
};

type CounterpartyLocationState = {
  resolution?: CounterpartyResolutionResult;
};

const writingStyles = Object.keys(REPORT_WRITING_STYLE_LABELS) as ReportWritingStyle[];
const exportFormats: ReportExportFormat[] = ["pdf", "docx"];
const caseStatuses: CddCaseStatus[] = ["draft", "in_review", "needs_follow_up", "ready_for_export", "archived"];

const caseStatusLabels: Record<CddCaseStatus, string> = {
  draft: "Draft",
  in_review: "In review",
  needs_follow_up: "Needs follow-up",
  ready_for_export: "Ready for export",
  archived: "Archived",
};

function candidateIdentifier(candidate: CounterpartyResolutionCandidate): string {
  return candidate.uen ?? candidate.officialIdentifier ?? candidate.entityName;
}

function uniqueStrings(values: readonly (string | null | undefined)[]): string[] {
  return Array.from(new Set(values.filter((value): value is string =>
    typeof value === "string" && value.trim() !== "",
  ).map((value) => value.trim())));
}

function stringifyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function downloadText(filename: string, mimeType: string, text: string): void {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function valueForDisplay(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") {
    return <span className="muted">Not returned</span>;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return <pre>{stringifyJson(value)}</pre>;
}

function SummaryTable({ rows }: { rows: readonly BriefSummaryItem[] }) {
  if (rows.length === 0) {
    return <p className="muted">No rows returned.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th scope="col">Field</th>
          <th scope="col">Value</th>
          <th scope="col">Source</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={`${row.label}-${index}`}>
            <th scope="row">{row.label}</th>
            <td>{valueForDisplay(row.value)}</td>
            <td>{row.source ?? "Not returned"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RecordTable({ records }: { records: readonly object[] }) {
  if (records.length === 0) {
    return <p className="muted">No records returned.</p>;
  }

  const normalizedRecords = records.map((record) => record as Record<string, unknown>);
  const keys = Array.from(new Set(normalizedRecords.flatMap((record) => Object.keys(record))));

  return (
    <table>
      <thead>
        <tr>
          {keys.map((key) => (
            <th key={key} scope="col">
              {key}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {normalizedRecords.map((record, rowIndex) => (
          <tr key={rowIndex}>
            {keys.map((key) => (
              <td key={key}>{valueForDisplay(record[key])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PlainList({ emptyText, items }: { emptyText: string; items: readonly string[] }) {
  if (items.length === 0) {
    return <p className="muted">{emptyText}</p>;
  }

  return (
    <ul>
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  );
}

function responseFromCaseRecord(record: CddCaseRecord): CddOrchestratorResponse | null {
  if (
    record.dossier === undefined ||
    record.memoState === undefined ||
    record.evidencePack.webPresence === undefined ||
    record.evidencePack.peopleDiscovery === undefined ||
    record.evidencePack.orchestration === undefined
  ) {
    return null;
  }

  return {
    dossier: record.dossier,
    generatedAt: record.evidencePack.generatedAt ?? record.updatedAt,
    memo: record.memoState,
    orchestration: record.evidencePack.orchestration,
    peopleDiscovery: record.evidencePack.peopleDiscovery,
    webPresence: record.evidencePack.webPresence,
    ...(record.selectedCandidate === null ? {} : {
      resolution: {
        status: "resolved",
        originalInput: record.counterpartyIdentifier,
        normalizedInput: record.counterpartyIdentifier.toLowerCase(),
        selectedCandidate: record.selectedCandidate,
        candidates: [record.selectedCandidate],
        confidenceBlockers: [],
        sourcesSearched: [record.selectedCandidate.sourceRegistry],
        limits: [],
      } satisfies CounterpartyResolutionResult,
    }),
  };
}

export function CounterpartyPage() {
  const { caseId: routeCaseId, identifier = "" } = useParams<{ caseId?: string; identifier?: string }>();
  const decodedIdentifier = useMemo(() => identifier.trim(), [identifier]);
  const [caseRecord, setCaseRecord] = useState<CddCaseRecord | null>(null);
  const [state, setState] = useState<DossierState>({ status: "loading" });
  const location = useLocation();

  useEffect(() => {
    const controller = new AbortController();
    const routeState = location.state as CounterpartyLocationState | null;
    const stateResolution = routeState?.resolution;
    const session = resolveActiveSession();
    let store = loadWorkspaceStore();
    let activeCaseId = routeCaseId;
    let activeCase = routeCaseId === undefined ? null : getCddCase(store, session, routeCaseId);
    const activeIdentifier = activeCase?.counterpartyIdentifier ?? decodedIdentifier;

    if (activeIdentifier === "") {
      setState({ status: "error", message: "No counterparty identifier was provided." });
      return () => controller.abort();
    }

    if (routeCaseId !== undefined && activeCase === null) {
      setState({ status: "error", message: `CDD case ${routeCaseId} was not found in browser-local storage.` });
      return () => controller.abort();
    }

    if (activeCaseId === undefined) {
      store = upsertCddCase(store, session, { counterpartyIdentifier: activeIdentifier });
      activeCaseId = buildCddCaseId(session, { counterpartyIdentifier: activeIdentifier });
      saveWorkspaceStore(store);
      activeCase = getCddCase(store, session, activeCaseId);
    }

    setCaseRecord(activeCase);

    const storedResponse = activeCase === null ? null : responseFromCaseRecord(activeCase);
    if (routeCaseId !== undefined && storedResponse !== null) {
      setState(isNotFoundDossier(storedResponse.dossier)
        ? { status: "not-found", dossier: storedResponse.dossier, response: storedResponse }
        : { status: "success", dossier: storedResponse.dossier, response: storedResponse });
      return () => controller.abort();
    }

    setState({ status: "loading" });

    const loadDossier = async () => {
      const resolution = stateResolution?.status === "resolved" && stateResolution.selectedCandidate !== null
        ? stateResolution
        : await postGatewayJson<CounterpartyResolutionResult>(
            "/api/v1/dude/resolve-counterparty",
            { identifier: activeIdentifier },
            { signal: controller.signal },
          );

      if (controller.signal.aborted) return;

      if (resolution.status === "needs_confirmation") {
        setState({ status: "needs-confirmation", resolution });
        return;
      }

      if (resolution.status === "no_match" || resolution.selectedCandidate === null) {
        setState({
          status: "error",
          message: `No retained CDD registry match was found for "${activeIdentifier}".`,
        });
        return;
      }

      if (activeCaseId !== undefined && routeCaseId === undefined) {
        const withCandidate = upsertCddCase(loadWorkspaceStore(), session, {
          counterpartyIdentifier: activeIdentifier,
          selectedCandidate: resolution.selectedCandidate,
        });
        saveWorkspaceStore(withCandidate);
        setCaseRecord(getCddCase(withCandidate, session, activeCaseId));
      }

      const response = await postGatewayJson<CddOrchestratorResponse>(
        "/api/v1/dude/cdd-orchestrator",
        {
          confirmedCandidate: resolution.selectedCandidate,
          identifier: resolution.originalInput || activeIdentifier,
        },
        { signal: controller.signal },
      );

      if (controller.signal.aborted) return;

      if (activeCaseId !== undefined) {
        const withDossier = attachDossierToCddCase(loadWorkspaceStore(), session, activeCaseId, {
          counterpartyIdentifier: activeIdentifier,
          dossier: response.dossier,
          generatedAt: response.generatedAt,
          memoState: response.memo,
          orchestration: response.orchestration,
          peopleDiscovery: response.peopleDiscovery,
          selectedCandidate: resolution.selectedCandidate,
          webPresence: response.webPresence,
        });
        saveWorkspaceStore(withDossier);
        setCaseRecord(getCddCase(withDossier, session, activeCaseId));
      }

      setState(isNotFoundDossier(response.dossier)
        ? { status: "not-found", dossier: response.dossier, response }
        : { status: "success", dossier: response.dossier, response });
    };

    void loadDossier().catch((error: unknown) => {
      if (controller.signal.aborted) return;
      setState({
        status: "error",
        message: error instanceof Error ? error.message : "The CDD orchestrator request failed.",
      });
    });

    return () => controller.abort();
  }, [decodedIdentifier, location.state, routeCaseId]);

  return (
    <main>
      <p>
        <Link to="/">New search</Link>
      </p>
      {state.status === "loading" ? (
        <LoadingView identifier={caseRecord?.counterpartyIdentifier ?? decodedIdentifier} />
      ) : state.status === "needs-confirmation" ? (
        <ResolutionConfirmation identifier={caseRecord?.counterpartyIdentifier ?? decodedIdentifier} resolution={state.resolution} />
      ) : state.status === "error" ? (
        <ProblemView identifier={caseRecord?.counterpartyIdentifier ?? decodedIdentifier} message={state.message} />
      ) : state.status === "not-found" ? (
        <DossierView
          caseRecord={caseRecord}
          dossier={state.dossier}
          identifier={caseRecord?.counterpartyIdentifier ?? decodedIdentifier}
          notFound
          onCaseRecordChange={setCaseRecord}
          response={state.response}
        />
      ) : (
        <DossierView
          caseRecord={caseRecord}
          dossier={state.dossier}
          identifier={caseRecord?.counterpartyIdentifier ?? decodedIdentifier}
          onCaseRecordChange={setCaseRecord}
          response={state.response}
        />
      )}
    </main>
  );
}

function LoadingView({ identifier }: { identifier: string }) {
  return (
    <section aria-busy="true">
      <h1>Running CDD orchestrator</h1>
      <p>{identifier}</p>
      <p className="muted">
        Resolving the counterparty, then requesting one CDD orchestrator response from the REST gateway.
      </p>
    </section>
  );
}

function ProblemView({ identifier, message }: { identifier: string; message: string }) {
  return (
    <section>
      <h1>CDD request failed</h1>
      <p>
        <strong>Identifier:</strong> {identifier}
      </p>
      <p className="error">{message}</p>
      <SafetyNotice />
    </section>
  );
}

function ResolutionConfirmation({
  identifier,
  resolution,
}: {
  identifier: string;
  resolution: CounterpartyResolutionResult;
}) {
  const navigate = useNavigate();

  const handleCandidateClick = (candidate: CounterpartyResolutionCandidate) => {
    navigate(`/c/${encodeURIComponent(candidateIdentifier(candidate))}`, {
      replace: true,
      state: {
        resolution: {
          ...resolution,
          candidates: [candidate],
          confidenceBlockers: candidate.matchMethod === "typo"
            ? ["The selected candidate relied on bounded typo matching; verify source rows before final decisions."]
            : [],
          selectedCandidate: candidate,
          status: "resolved",
        } satisfies CounterpartyResolutionResult,
      },
    });
  };

  return (
    <section>
      <h1>Confirm official match</h1>
      <p>Multiple retained CDD registry candidates matched "{identifier}". Choose one to run the orchestrator.</p>
      <table>
        <thead>
          <tr>
            <th scope="col">Candidate</th>
            <th scope="col">Source</th>
            <th scope="col">Identifier</th>
            <th scope="col">Reason</th>
            <th scope="col">Action</th>
          </tr>
        </thead>
        <tbody>
          {resolution.candidates.map((candidate) => (
            <tr key={candidate.id}>
              <td>{candidate.label}</td>
              <td>{candidate.sourceRegistry}</td>
              <td>{candidate.uen ?? candidate.officialIdentifier ?? "Not returned"}</td>
              <td>{candidate.matchReason}</td>
              <td>
                <button onClick={() => handleCandidateClick(candidate)} type="button">
                  Use this match
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <SafetyNotice />
    </section>
  );
}

function DossierView({
  caseRecord,
  dossier,
  identifier,
  notFound = false,
  onCaseRecordChange,
  response,
}: {
  caseRecord: CddCaseRecord | null;
  dossier: BusinessDossier;
  identifier: string;
  notFound?: boolean;
  onCaseRecordChange: (record: CddCaseRecord | null) => void;
  response: CddOrchestratorResponse;
}) {
  const [writingStyle, setWritingStyle] = useState<ReportWritingStyle>("concise_analyst");
  const [exportFormat, setExportFormat] = useState<ReportExportFormat>("pdf");
  const [isExporting, setIsExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const memo = response.memo;
  const entityName = getSummaryString(dossier, "Entity") ?? dossier.title;
  const uen = getSummaryString(dossier, "UEN");
  const confidenceBlockers = uniqueStrings([
    ...(response.resolution?.confidenceBlockers ?? []),
    ...(memo.status === "ready" ? memo.riskRating.confidenceBlockers : []),
    ...(memo.status === "ready" ? memo.decisionAid.confidenceBlockers : []),
  ]);
  const analystFollowUps = uniqueStrings([
    ...getAnalystFollowUps(dossier).map((followUp) =>
      `[${followUpPriorityLabel(followUp.priority)}] ${followUp.action} Evidence gap: ${followUp.reason} Why this matters: ${followUp.whyThisMatters}`,
    ),
    ...(memo.status === "ready" ? memo.decisionAid.nextSteps : []),
  ]);

  const commitCaseStore = (update: (store: ReturnType<typeof loadWorkspaceStore>) => ReturnType<typeof loadWorkspaceStore>) => {
    if (caseRecord === null) return;
    const nextStore = update(loadWorkspaceStore());
    saveWorkspaceStore(nextStore);
    onCaseRecordChange(getCddCase(nextStore, resolveActiveSession(), caseRecord.id));
  };

  const handleExport = async () => {
    setIsExporting(true);
    setExportMessage(null);
    const today = new Date().toISOString().slice(0, 10);
    const reportTemplate: ReportTemplate = {
      ...DEFAULT_REPORT_TEMPLATE,
      writingStyle,
    };

    try {
      const filename = `dude-cdd-report-${sanitizeFilenamePart(identifier)}-${today}.${exportFormat}`;
      if (exportFormat === "pdf") {
        const { exportDossierPdf } = await import("@/lib/export/pdf");
        await exportDossierPdf(dossier, {
          ...(memo.status === "ready" ? { analystMemo: memo } : {}),
          filename,
          orchestration: response.orchestration,
          reportTemplate,
          webPresence: response.webPresence,
        });
      } else {
        const { exportDossierDocx } = await import("@/lib/export/docx");
        await exportDossierDocx(dossier, {
          ...(memo.status === "ready" ? { analystMemo: memo } : {}),
          filename,
          orchestration: response.orchestration,
          reportTemplate,
          webPresence: response.webPresence,
        });
      }
      commitCaseStore((store) => recordCddCaseExport(store, resolveActiveSession(), caseRecord!.id, {
        filename,
        format: exportFormat,
        packageType: "report_package",
        writingStyle,
      }));
      setExportMessage(`${exportFormat.toUpperCase()} export started.`);
    } catch (error) {
      setExportMessage(error instanceof Error ? error.message : "Report export failed.");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <>
      <header>
        <h1>{dossier.title}</h1>
        <p>
          <strong>Requested identifier:</strong> {identifier}
        </p>
        <p>
          <strong>Entity:</strong> {entityName}
          {uen === null ? null : <> | <strong>UEN:</strong> {uen}</>}
        </p>
        {notFound ? (
          <p className="error">
            No matched retained registry records were returned. Review gaps, source coverage, and limits before deciding
            next steps.
          </p>
        ) : null}
        <SafetyNotice />
      </header>

      {caseRecord === null ? null : (
        <CaseWorkflowSection
          caseRecord={caseRecord}
          onCaseRecordChange={onCaseRecordChange}
        />
      )}

      <section>
        <h2>Entity identity</h2>
        <SummaryTable rows={dossier.summary} />
      </section>

      <section>
        <h2>Source-backed summary</h2>
        {memo.status === "ready" ? (
          <>
            <p>
              <strong>Memo provider:</strong> {memo.provider} / {memo.model} / generated {formatRecordValue("generatedAt", memo.generatedAt)}
            </p>
            <p>
              <strong>Risk rating:</strong> {memo.riskRating.level} - {memo.riskRating.rationale}
            </p>
            <table>
              <thead>
                <tr>
                  <th scope="col">Finding</th>
                  <th scope="col">Citation IDs</th>
                </tr>
              </thead>
              <tbody>
                {memo.evidenceMemo.map((finding, index) => (
                  <tr key={`${finding.text}-${index}`}>
                    <td>{finding.text}</td>
                    <td>{finding.citationIds.join(", ") || "Not returned"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {memo.rejectedClaims.length === 0 ? null : (
              <details>
                <summary>Rejected claims</summary>
                <RecordTable records={memo.rejectedClaims} />
              </details>
            )}
          </>
        ) : (
          <>
            <p className="error">Analyst memo unavailable: {memo.reason.message}</p>
            <p className="muted">Showing backend summary and evidence rows without generated memo wording.</p>
            <SummaryTable rows={dossier.evidence} />
          </>
        )}
      </section>

      <section>
        <h2>Citations</h2>
        {memo.status === "ready" ? (
          <RecordTable records={memo.citations} />
        ) : (
          <p className="muted">No generated memo citations returned.</p>
        )}
      </section>

      <section>
        <h2>Confidence blockers</h2>
        <PlainList
          emptyText="No confidence blockers were returned by the backend. Analysts must still review evidence, gaps, limits, and citations before relying on the report."
          items={confidenceBlockers}
        />
      </section>

      <section>
        <h2>Analyst follow-ups</h2>
        <PlainList
          emptyText="No analyst follow-ups were returned. Review gaps, source coverage, and limits manually."
          items={analystFollowUps}
        />
        {dossier.nextChecks === undefined || dossier.nextChecks.length === 0 ? null : (
          <details>
            <summary>Legacy next-check inputs</summary>
            <pre>{stringifyJson(dossier.nextChecks)}</pre>
          </details>
        )}
      </section>

      <EvidenceRecordsSection dossier={dossier} />
      <SectorWorkflowSection dossier={dossier} />
      <SourceCoverageSection coverage={dossier.sourceCoverage ?? []} />
      <GapsLimitsSection dossier={dossier} memo={memo} response={response} />
      <ProvenanceFreshnessSection dossier={dossier} />
      <SupplementalEvidenceSection response={response} />
      <OrchestrationSection orchestration={response.orchestration} />

      <section>
        <h2>Export report</h2>
        <p className="muted">Uses the existing PDF/DOCX export code with the standard CDD report sections.</p>
        <label htmlFor="writing-style">Writing style</label>
        <select
          id="writing-style"
          onChange={(event) => setWritingStyle(event.target.value as ReportWritingStyle)}
          value={writingStyle}
        >
          {writingStyles.map((style) => (
            <option key={style} value={style}>
              {REPORT_WRITING_STYLE_LABELS[style]}
            </option>
          ))}
        </select>
        <label htmlFor="export-format">Format</label>
        <select
          id="export-format"
          onChange={(event) => setExportFormat(event.target.value as ReportExportFormat)}
          value={exportFormat}
        >
          {exportFormats.map((format) => (
            <option key={format} value={format}>
              {format.toUpperCase()}
            </option>
          ))}
        </select>
        <button disabled={isExporting} onClick={() => void handleExport()} type="button">
          {isExporting ? "Exporting..." : "Export report"}
        </button>
        {exportMessage === null ? null : (
          <p className={exportMessage.toLowerCase().includes("failed") ? "error" : "notice"}>{exportMessage}</p>
        )}
      </section>

      <details>
        <summary>Raw orchestrator response</summary>
        <pre>{stringifyJson(response)}</pre>
      </details>
    </>
  );
}

function CaseWorkflowSection({
  caseRecord,
  onCaseRecordChange,
}: {
  caseRecord: CddCaseRecord;
  onCaseRecordChange: (record: CddCaseRecord | null) => void;
}) {
  const [noteBody, setNoteBody] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const openTaskCount = caseRecord.followUpTasks.filter((task) => task.status === "open").length;
  const completedTaskCount = caseRecord.followUpTasks.length - openTaskCount;
  const reportReadinessBlockers = [
    caseRecord.dossier === undefined ? "Run and attach a CDD dossier." : null,
    openTaskCount > 0 ? `${openTaskCount} follow-up task${openTaskCount === 1 ? "" : "s"} still open.` : null,
    caseRecord.status !== "ready_for_export" ? "Case status is not marked ready for export." : null,
  ].filter((item): item is string => item !== null);

  const commitCaseStore = (
    update: (store: ReturnType<typeof loadWorkspaceStore>, session: ReturnType<typeof resolveActiveSession>) => ReturnType<typeof loadWorkspaceStore>,
  ) => {
    const session = resolveActiveSession();
    const nextStore = update(loadWorkspaceStore(), session);
    saveWorkspaceStore(nextStore);
    onCaseRecordChange(getCddCase(nextStore, session, caseRecord.id));
  };

  const handleStatusChange = (status: CddCaseStatus) => {
    commitCaseStore((store, session) => updateCddCaseStatus(store, session, caseRecord.id, status));
  };

  const handleAddNote = () => {
    commitCaseStore((store, session) => addCddCaseNote(store, session, caseRecord.id, noteBody));
    setNoteBody("");
  };

  const handleAddTask = () => {
    commitCaseStore((store, session) => addCddCaseTask(store, session, caseRecord.id, {
      description: taskDescription,
      title: taskTitle,
    }));
    setTaskTitle("");
    setTaskDescription("");
  };

  const handleTaskToggle = (taskId: string, completed: boolean) => {
    commitCaseStore((store, session) =>
      setCddCaseTaskCompleted(store, session, caseRecord.id, taskId, completed),
    );
  };

  const handleExportCaseJson = () => {
    const exportedAt = new Date().toISOString();
    const filename = `dude-cdd-case-${sanitizeFilenamePart(caseRecord.candidateIdentifier ?? caseRecord.counterpartyIdentifier)}-${exportedAt.slice(0, 10)}.json`;
    const session = resolveActiveSession();
    const nextStore = recordCddCaseExport(loadWorkspaceStore(), session, caseRecord.id, {
      filename,
      format: "json",
      packageType: "case_json",
      now: exportedAt,
    });
    saveWorkspaceStore(nextStore);
    const updatedCase = getCddCase(nextStore, session, caseRecord.id) ?? caseRecord;
    onCaseRecordChange(updatedCase);
    downloadText(
      filename,
      "application/json",
      JSON.stringify(buildCddCaseJsonPackage(updatedCase, exportedAt), null, 2),
    );
  };

  return (
    <section>
      <h2>Case workflow</h2>
      <p className="muted">
        Workspace storage is browser-local. Case status, notes, tasks, exports, and audit events are workflow metadata;
        they do not modify source facts or imply approval, rejection, compliance clearance, or licensed advice.
      </p>

      <div className="case-grid">
        <div>
          <label htmlFor="case-status">Case status</label>
          <select
            id="case-status"
            onChange={(event) => handleStatusChange(event.target.value as CddCaseStatus)}
            value={caseRecord.status}
          >
            {caseStatuses.map((status) => (
              <option key={status} value={status}>
                {caseStatusLabels[status]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <h3>Report readiness</h3>
          {reportReadinessBlockers.length === 0 ? (
            <p className="notice">Ready for export package handoff. This is not a clearance decision.</p>
          ) : (
            <PlainList emptyText="No readiness blockers." items={reportReadinessBlockers} />
          )}
        </div>
        <div>
          <h3>Case identifiers</h3>
          <p>
            <strong>Case ID:</strong> {caseRecord.id}
          </p>
          <p>
            <strong>Counterparty:</strong> {caseRecord.counterpartyIdentifier}
          </p>
          <p>
            <strong>Selected candidate:</strong> {caseRecord.candidateIdentifier ?? "Not selected"}
          </p>
          <p>
            <strong>Storage:</strong> browser-local workspace
          </p>
        </div>
      </div>

      <div className="case-subsection">
        <h3>Review notes</h3>
        <p className="muted">Analyst notes are stored separately from registry, supplemental, and memo evidence.</p>
        <label htmlFor="case-note">Add note</label>
        <textarea
          id="case-note"
          onChange={(event) => setNoteBody(event.target.value)}
          rows={3}
          value={noteBody}
        />
        <button disabled={noteBody.trim() === ""} onClick={handleAddNote} type="button">
          Add note
        </button>
        {caseRecord.analystNotes.length === 0 ? (
          <p className="muted">No analyst notes yet.</p>
        ) : (
          <ul>
            {caseRecord.analystNotes.map((note) => (
              <li key={note.id}>
                <strong>{formatRecordValue("createdAt", note.createdAt)}:</strong> {note.body}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="case-subsection">
        <h3>Follow-up tasks</h3>
        <p className="muted">
          Tasks can reference dossier or memo follow-ups, but completion is analyst workflow state only.
        </p>
        <p>
          <strong>{completedTaskCount}</strong> complete / <strong>{openTaskCount}</strong> open
        </p>
        {caseRecord.followUpTasks.length === 0 ? (
          <p className="muted">No follow-up tasks have been created.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th scope="col">Done</th>
                <th scope="col">Task</th>
                <th scope="col">Source</th>
                <th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {caseRecord.followUpTasks.map((task) => (
                <tr key={task.id}>
                  <td>
                    <input
                      aria-label={`Mark ${task.title} complete`}
                      checked={task.status === "completed"}
                      onChange={(event) => handleTaskToggle(task.id, event.target.checked)}
                      type="checkbox"
                    />
                  </td>
                  <td>{task.title}</td>
                  <td>{task.source}</td>
                  <td>{task.description ?? task.sourceRef ?? "No details"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <label htmlFor="case-task-title">Add task</label>
        <input
          id="case-task-title"
          onChange={(event) => setTaskTitle(event.target.value)}
          placeholder="Follow up with corporate secretary"
          value={taskTitle}
        />
        <label htmlFor="case-task-description">Task details</label>
        <textarea
          id="case-task-description"
          onChange={(event) => setTaskDescription(event.target.value)}
          rows={2}
          value={taskDescription}
        />
        <button disabled={taskTitle.trim() === ""} onClick={handleAddTask} type="button">
          Add follow-up task
        </button>
      </div>

      <div className="case-subsection">
        <h3>Export and audit handoff</h3>
        <p className="muted">
          Export the case JSON to move browser-local workflow state between analysts or preserve an audit handoff package.
        </p>
        <button onClick={handleExportCaseJson} type="button">
          Export case JSON
        </button>
        {caseRecord.exports.length === 0 ? (
          <p className="muted">No exports recorded yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th scope="col">Exported</th>
                <th scope="col">Format</th>
                <th scope="col">File</th>
                <th scope="col">Status at export</th>
              </tr>
            </thead>
            <tbody>
              {caseRecord.exports.map((item) => (
                <tr key={item.id}>
                  <td>{formatRecordValue("exportedAt", item.exportedAt)}</td>
                  <td>{item.format.toUpperCase()}</td>
                  <td>{item.filename}</td>
                  <td>{caseStatusLabels[item.statusAtExport]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <details>
          <summary>Case audit events</summary>
          <RecordTable records={caseRecord.auditEvents} />
        </details>
      </div>
    </section>
  );
}

function SafetyNotice() {
  return (
    <p className="notice">
      No clearance is implied. Dude does not provide legal, tax, AML, sanctions, credit,
      investment, or licensed-advisor advice. Absence of public evidence is not a positive
      clearance finding.
    </p>
  );
}

function EvidenceRecordsSection({ dossier }: { dossier: BusinessDossier }) {
  const groups = getDossierRecordGroups(dossier);

  return (
    <section>
      <h2>Evidence records</h2>
      <SummaryTable rows={dossier.evidence} />
      {groups.map((group) => (
        <details key={group.module} open={group.module === "acra"}>
          <summary>{group.label}</summary>
          {group.tables.map((table) => (
            <section key={table.label}>
              <h3>{table.label}</h3>
              <RecordTable records={table.records} />
            </section>
          ))}
        </details>
      ))}
      <details>
        <summary>Raw dossier records</summary>
        <pre>{stringifyJson(dossier.records)}</pre>
      </details>
    </section>
  );
}

const moduleReasonLabels: Record<BusinessDossierModuleReason["selectedBy"][number], string> = {
  analyst_rerun: "analyst rerun",
  default: "default identity lookup",
  explicit_module: "explicit user choice",
  inferred_sector: "ACRA/SSIC inference",
  sector_hint: "explicit sector hint",
  web_hint: "web hint",
};

function moduleReasonStatusLabel(status: BusinessDossierModuleReason["status"]): string {
  if (status === "matched") return "matched";
  if (status === "unmatched") return "no match";
  if (status === "needs_identifier") return "needs identifier";
  if (status === "unsearched") return "not searched";
  return "skipped";
}

function moduleReasonSelection(reason: BusinessDossierModuleReason): string {
  return reason.selectedBy.length === 0
    ? "not selected"
    : reason.selectedBy.map((item) => moduleReasonLabels[item]).join(", ");
}

function SectorWorkflowSection({ dossier }: { dossier: BusinessDossier }) {
  const guide = dossier.records.resolution?.sectorWorkflowGuide ?? [];
  const reasons = dossier.records.resolution?.moduleReasons ?? [];

  return (
    <section>
      <h2>Sector workflow guide</h2>
      <p className="muted">
        Sector inference is bounded and reversible. Rerun with explicit sector hints and source-specific identifiers
        when a sector check is relevant but missing evidence.
      </p>
      {guide.length === 0 ? (
        <p className="muted">No sector workflow guide returned.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Sector</th>
              <th scope="col">Retained modules</th>
              <th scope="col">Required identifiers</th>
              <th scope="col">Source-bound use</th>
            </tr>
          </thead>
          <tbody>
            {guide.map((item: SectorWorkflowGuideItem) => (
              <tr key={item.sector}>
                <th scope="row">{item.label}</th>
                <td>{item.retainedModules.join(", ")} / {item.retainedTools.join(", ")}</td>
                <td>{item.requiredIdentifiers.join("; ")}</td>
                <td>{item.sourceBoundUse}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {reasons.length === 0 ? null : (
        <>
          <h3>Sector module status</h3>
          <table>
            <thead>
              <tr>
                <th scope="col">Module</th>
                <th scope="col">Status</th>
                <th scope="col">Selected by</th>
                <th scope="col">Next step</th>
              </tr>
            </thead>
            <tbody>
              {reasons.map((reason) => (
                <tr key={reason.module}>
                  <th scope="row">{reason.module}</th>
                  <td>{moduleReasonStatusLabel(reason.status)}</td>
                  <td>{moduleReasonSelection(reason)}</td>
                  <td>
                    {reason.followUpPrompts?.join(" ") || reason.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function SourceCoverageSection({ coverage }: { coverage: readonly SourceCoverageItem[] }) {
  return (
    <section>
      <h2>Source coverage</h2>
      {coverage.length === 0 ? (
        <p className="muted">No source coverage matrix returned.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Source family</th>
              <th scope="col">Status</th>
              <th scope="col">Coverage</th>
              <th scope="col">Records</th>
              <th scope="col">Freshness</th>
              <th scope="col">Reason</th>
            </tr>
          </thead>
          <tbody>
            {coverage.map((item, index) => (
              <tr key={`${item.family}-${index}`}>
                <th scope="row">{item.label}</th>
                <td>{item.status}</td>
                <td>{item.coverageLevel}</td>
                <td>{item.recordCount}</td>
                <td>{item.sourceFreshness ?? item.checkedAt ?? "Not returned"}</td>
                <td>{item.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function GapsLimitsSection({
  dossier,
  memo,
  response,
}: {
  dossier: BusinessDossier;
  memo: AnalystMemoResponse;
  response: CddOrchestratorResponse;
}) {
  return (
    <section>
      <h2>Gaps and limits</h2>
      <h3>Gaps</h3>
      {dossier.gaps.length === 0 ? (
        <p className="muted">No dossier gaps returned.</p>
      ) : (
        <RecordTable records={dossier.gaps} />
      )}
      {memo.gaps.length === 0 ? null : (
        <details open>
          <summary>Memo gaps</summary>
          <RecordTable records={memo.gaps} />
        </details>
      )}
      <h3>Limits</h3>
      {dossier.limits.length === 0 ? (
        <p className="muted">No dossier limits returned.</p>
      ) : (
        <RecordTable records={dossier.limits} />
      )}
      {memo.limits.length === 0 ? null : (
        <details>
          <summary>Memo limits</summary>
          <RecordTable records={memo.limits} />
        </details>
      )}
      {response.orchestration.limits.length === 0 ? null : (
        <details>
          <summary>Orchestrator limits</summary>
          <PlainList emptyText="No orchestrator limits returned." items={response.orchestration.limits} />
        </details>
      )}
    </section>
  );
}

function ProvenanceFreshnessSection({ dossier }: { dossier: BusinessDossier }) {
  return (
    <section>
      <h2>Provenance and freshness</h2>
      <h3>Provenance</h3>
      {dossier.provenance.length === 0 ? (
        <p className="muted">No provenance returned.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Tool</th>
              <th scope="col">Coverage</th>
              <th scope="col">Records</th>
              <th scope="col">Auth required</th>
              <th scope="col">URL</th>
            </tr>
          </thead>
          <tbody>
            {dossier.provenance.map((item, index) => (
              <tr key={`${item.source}-${index}`}>
                <th scope="row">{item.source}</th>
                <td>{item.tool}</td>
                <td>{item.coverage}</td>
                <td>{item.recordCount}</td>
                <td>{item.authRequired ? "yes" : "no"}</td>
                <td>{item.sourceUrl ?? "Not returned"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Freshness</h3>
      {dossier.freshness.length === 0 ? (
        <p className="muted">No freshness timestamps returned.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Observed at</th>
              <th scope="col">Upstream timestamp</th>
            </tr>
          </thead>
          <tbody>
            {dossier.freshness.map((item, index) => (
              <tr key={`${item.source}-${index}`}>
                <th scope="row">{item.source}</th>
                <td>{formatRecordValue("observedAt", item.observedAt)}</td>
                <td>{formatRecordValue("upstreamTimestamp", item.upstreamTimestamp ?? null)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function SupplementalEvidenceSection({ response }: { response: CddOrchestratorResponse }) {
  return (
    <section>
      <h2>Supplemental evidence</h2>
      <p className="muted">
        Web presence and people-discovery results are supplemental analyst-review evidence, not official registry
        clearance.
      </p>
      <details open>
        <summary>Web presence</summary>
        <p>
          <strong>Query:</strong> {response.webPresence.query}
        </p>
        <p>
          <strong>Configured:</strong> {response.webPresence.configured ? "yes" : "no"}
        </p>
        <p>
          <strong>Possible official website:</strong>{" "}
          {response.webPresence.possibleOfficialWebsite ?? "Not returned"}
        </p>
        <RecordTable records={response.webPresence.results} />
        <PlainList emptyText="No web-presence limits returned." items={response.webPresence.limits} />
      </details>
      <details>
        <summary>People discovery</summary>
        <p>
          <strong>Query:</strong> {response.peopleDiscovery.query}
        </p>
        <p>
          <strong>Configured:</strong> {response.peopleDiscovery.configured ? "yes" : "no"}
        </p>
        <RecordTable records={response.peopleDiscovery.results} />
        <h3>Suggested actions</h3>
        <PlainList emptyText="No people-discovery actions returned." items={response.peopleDiscovery.suggestedActions} />
        <h3>Limits</h3>
        <PlainList emptyText="No people-discovery limits returned." items={response.peopleDiscovery.limits} />
      </details>
    </section>
  );
}

function OrchestrationSection({ orchestration }: { orchestration: CddOrchestrationTrace }) {
  return (
    <section>
      <h2>Orchestrator trace</h2>
      <table>
        <tbody>
          <tr>
            <th scope="row">Status</th>
            <td>{orchestration.status}</td>
          </tr>
          <tr>
            <th scope="row">Strategy</th>
            <td>{orchestration.strategy}</td>
          </tr>
          <tr>
            <th scope="row">Official modules</th>
            <td>{orchestration.officialModules.join(", ") || "None"}</td>
          </tr>
          <tr>
            <th scope="row">Supplemental tools</th>
            <td>{orchestration.supplementalTools.join(", ") || "None"}</td>
          </tr>
          <tr>
            <th scope="row">Effective sector hints</th>
            <td>{orchestration.effectiveSectorHints.join(", ") || "None"}</td>
          </tr>
        </tbody>
      </table>
      {orchestration.stages === undefined || orchestration.stages.length === 0 ? null : (
        <details>
          <summary>Stages</summary>
          <RecordTable records={orchestration.stages} />
        </details>
      )}
    </section>
  );
}
