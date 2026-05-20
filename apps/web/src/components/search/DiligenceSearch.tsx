import { ChangeEvent, FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, CornerDownLeft, Upload } from "lucide-react";

import { useToast } from "@/components/notifications/ToastProvider";
import { AiInput } from "@/components/ui/ai-input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getGatewayJson,
  postGatewayJson,
  type ApiSearchSuggestion,
  type CounterpartyResolutionCandidate,
  type CounterpartyResolutionResult,
} from "@/lib/api/client";
import { parseBulkInput } from "@/lib/bulk";
import { rankSearchSuggestions } from "@/lib/search/rank-search-suggestions";

type SearchStatus = "idle" | "submitting" | "error";
type SuggestionStatus = "idle" | "loading" | "ready" | "error";

type SuggestionResponse = {
  query: string;
  suggestions: ApiSearchSuggestion[];
  warning?: string;
};

type DiligenceSearchProps = {
  onBulkSubmit?: () => void;
  onValueChange?: (value: string) => void;
  secondaryAction?: ReactNode;
  showCsvUpload?: boolean;
  value?: string;
};

export function DiligenceSearch({
  onBulkSubmit,
  onValueChange,
  secondaryAction,
  showCsvUpload = true,
  value,
}: DiligenceSearchProps = {}) {
  const [internalQuery, setInternalQuery] = useState("");
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [suggestionStatus, setSuggestionStatus] = useState<SuggestionStatus>("idle");
  const [suggestions, setSuggestions] = useState<ApiSearchSuggestion[]>([]);
  const [resolution, setResolution] = useState<CounterpartyResolutionResult | null>(null);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { notify } = useToast();
  const query = value ?? internalQuery;
  const isSubmitting = status === "submitting";
  const trimmedQuery = query.trim();
  const parsedInput = useMemo(() => parseBulkInput(query), [query]);
  const canLookupSuggestions = trimmedQuery.length >= 2 && parsedInput.items.length <= 1 && !trimmedQuery.includes("\n");

  const updateQuery = (nextValue: string) => {
    if (onValueChange !== undefined) {
      onValueChange(nextValue);
    } else {
      setInternalQuery(nextValue);
    }
  };

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2 || parsedInput.items.length > 1 || trimmed.includes("\n")) {
      setSuggestions([]);
      setSuggestionStatus("idle");
      setSuggestionError(null);
      return;
    }

    const controller = new AbortController();
    setSuggestions([]);
    setSuggestionStatus("loading");
    setSuggestionError(null);

    const timer = window.setTimeout(() => {
      void getGatewayJson<SuggestionResponse>(
        "/api/v1/dude/search-suggestions",
        { q: trimmed },
        { signal: controller.signal },
      )
        .then((response) => {
          if (!controller.signal.aborted) {
            setSuggestions(response.suggestions);
            setSuggestionStatus("ready");
            setSuggestionError(null);
          }
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) {
            setSuggestions([]);
            setSuggestionStatus("error");
            setSuggestionError(error instanceof Error ? error.message : "Suggestions are temporarily unavailable.");
          }
        });
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [parsedInput.items.length, query]);

  const rankedSuggestions = useMemo(() => {
    const ranked = rankSearchSuggestions(
      query,
      suggestions.map((suggestion) => ({
        ...suggestion,
        aliases: [suggestion.uen, suggestion.status, suggestion.entityTypeDescription],
      })),
      6,
    );
    return ranked
      .map((rankedSuggestion) => suggestions.find((suggestion) => suggestion.id === rankedSuggestion.id))
      .filter((suggestion): suggestion is ApiSearchSuggestion => suggestion !== undefined);
  }, [query, suggestions]);

  const candidateIdentifier = (candidate: CounterpartyResolutionCandidate): string =>
    candidate.uen ?? candidate.entityName;

  const navigateToCandidate = (
    candidate: CounterpartyResolutionCandidate,
    originalInput: string,
    resolved?: CounterpartyResolutionResult,
  ) => {
    navigate(`/c/${encodeURIComponent(candidateIdentifier(candidate))}`, {
      state: {
        resolution: resolved ?? {
          status: "resolved",
          originalInput,
          normalizedInput: originalInput.trim().toLowerCase(),
          selectedCandidate: candidate,
          candidates: [candidate],
          confidenceBlockers: [],
          sourcesSearched: [candidate.sourceRegistry],
          limits: ["Candidate was selected before opening the dossier."],
        } satisfies CounterpartyResolutionResult,
      },
    });
  };

  const runSearch = async () => {
    if (!trimmedQuery) {
      setStatus("error");
      setError("Enter a client or counterparty company name or UEN.");
      notify({
        title: "Search needs an identifier",
        description: "Enter a Singapore company name or UEN before opening a dossier.",
        tone: "warning",
      });
      return;
    }

    if (parsedInput.errors.length > 0) {
      setStatus("error");
      setError("Fix the highlighted bulk rows before running diligence.");
      notify({
        title: "Bulk input has parse errors",
        description: `${parsedInput.errors.length} rows need attention before a bulk run.`,
        tone: "warning",
      });
      return;
    }

    if (parsedInput.items.length > 1) {
      setStatus("idle");
      setError(null);
      if (onBulkSubmit !== undefined) {
        onBulkSubmit();
        notify({
          title: "Bulk diligence started",
          description: `${parsedInput.items.length} counterparties queued from the search bar.`,
          tone: "info",
        });
      } else {
        setStatus("error");
        setError("Multiple rows need bulk execution support.");
      }
      return;
    }

    const identifier = parsedInput.items[0]?.identifier ?? trimmedQuery;

    setStatus("submitting");
    setError(null);
    setResolution(null);

    try {
      const resolved = await postGatewayJson<CounterpartyResolutionResult>(
        "/api/v1/dude/resolve-counterparty",
        { identifier },
      );
      if (resolved.status === "resolved" && resolved.selectedCandidate !== null) {
        navigateToCandidate(resolved.selectedCandidate, identifier, resolved);
        return;
      }
      if (resolved.status === "needs_confirmation") {
        setStatus("idle");
        setResolution(resolved);
        return;
      }
      setStatus("error");
      setError(`No retained CDD registry match was found for "${identifier}".`);
      notify({
        title: "No registry match",
        description: "Try a fuller Singapore company name or exact UEN.",
        tone: "warning",
      });
    } catch (err) {
      setStatus("error");
      const message = err instanceof Error ? err.message : "Navigation failed.";
      setError(message);
      notify({ title: "Search failed", description: message, tone: "error" });
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runSearch();
  };

  const shouldShowSearchPanel = isSubmitting || error !== null || resolution !== null || canLookupSuggestions || suggestionStatus !== "idle";

  const handleSuggestionClick = (suggestion: ApiSearchSuggestion) => {
    updateQuery(suggestion.entityName);
    navigate(`/c/${encodeURIComponent(suggestion.uen)}`);
  };

  const dropdownContent = shouldShowSearchPanel ? (
    <SearchDropdownContent
      error={error}
      isSubmitting={isSubmitting}
      onResolutionCandidateClick={(candidate) => navigateToCandidate(candidate, resolution?.originalInput ?? trimmedQuery)}
      onRunSearch={() => void runSearch()}
      onSuggestionClick={handleSuggestionClick}
      rankedSuggestions={rankedSuggestions}
      resolution={resolution}
      suggestionError={suggestionError}
      suggestionStatus={suggestionStatus}
      trimmedQuery={trimmedQuery}
    />
  ) : null;

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <AiInput
          aria-label="Client or counterparty company name or UEN"
          autoComplete="off"
          disabled={isSubmitting}
          dropdownContent={dropdownContent}
          isSubmitting={isSubmitting}
          onSubmit={() => void runSearch()}
          onValueChange={(nextQuery) => {
            updateQuery(nextQuery);
            setResolution(null);
            if (status === "error") {
              setStatus("idle");
              setError(null);
            }
          }}
          placeholder="Company name, UEN, or multiple rows"
          secondaryAction={secondaryAction ?? (showCsvUpload ? (
            <CsvUploadDialog
              onBulkSubmit={onBulkSubmit}
              onLoaded={(text) => {
                updateQuery(text);
                if (status === "error") {
                  setStatus("idle");
                  setError(null);
                }
              }}
            />
          ) : null)}
          value={query}
        />
      </form>
    </div>
  );
}

function CsvUploadDialog({
  onBulkSubmit,
  onLoaded,
}: {
  onBulkSubmit?: () => void;
  onLoaded: (text: string) => void;
}) {
  const [fileName, setFileName] = useState<string | null>(null);
  const [loadedText, setLoadedText] = useState("");
  const [open, setOpen] = useState(false);
  const parsed = useMemo(() => parseBulkInput(loadedText), [loadedText]);
  const { notify } = useToast();

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file === undefined) return;
    const text = await file.text();
    setFileName(file.name);
    setLoadedText(text);
    onLoaded(text);
    notify({ title: "CSV loaded into search", description: file.name, tone: "success" });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          aria-label="Upload CSV for bulk diligence"
          className="h-12 gap-2 px-4"
          type="button"
          variant="outline"
        >
          <Upload className="h-4 w-4" />
          <span>CSV</span>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload counterparties</DialogTitle>
          <DialogDescription>
            Load a CSV or text file into the search bar. Use one company name or UEN per row, or include an identifier column.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <label className="flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/30 px-4 py-5 text-center transition hover:bg-muted/50">
            <Upload aria-hidden="true" className="h-5 w-5 text-muted-foreground" />
            <span className="mt-2 text-sm font-medium text-foreground">Choose CSV</span>
            <span className="mt-1 text-xs text-muted-foreground">{fileName ?? "CSV, TXT, or newline-separated paste export"}</span>
            <input
              accept=".csv,text/csv,text/plain"
              aria-label="Choose CSV file"
              className="sr-only"
              onChange={handleFile}
              type="file"
            />
          </label>

          {loadedText === "" ? null : (
            <div className="rounded-md border border-border bg-background p-3 text-sm">
              <p className="font-medium text-foreground">
                {parsed.items.length} valid rows, {parsed.errors.length} parse errors
              </p>
              {parsed.errors.length === 0 ? (
                <p className="mt-1 text-muted-foreground">Rows are now in the search bar. Press Enter or run the bulk check from here.</p>
              ) : (
                <p className="mt-1 text-destructive">Fix parse errors in the search bar before running.</p>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)} type="button" variant="outline">Close</Button>
            <Button
              disabled={loadedText === "" || parsed.items.length === 0 || parsed.errors.length > 0 || onBulkSubmit === undefined}
              onClick={() => {
                onBulkSubmit?.();
                setOpen(false);
              }}
              type="button"
            >
              Run bulk check
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SearchDropdownContent({
  error,
  isSubmitting,
  onResolutionCandidateClick,
  onRunSearch,
  onSuggestionClick,
  rankedSuggestions,
  resolution,
  suggestionError,
  suggestionStatus,
  trimmedQuery,
}: {
  error: string | null;
  isSubmitting: boolean;
  onResolutionCandidateClick: (candidate: CounterpartyResolutionCandidate) => void;
  onRunSearch: () => void;
  onSuggestionClick: (suggestion: ApiSearchSuggestion) => void;
  rankedSuggestions: ApiSearchSuggestion[];
  resolution: CounterpartyResolutionResult | null;
  suggestionError: string | null;
  suggestionStatus: SuggestionStatus;
  trimmedQuery: string;
}) {
  if (isSubmitting) {
    return (
      <div aria-live="polite" className="space-y-3 px-4 py-4">
        <Skeleton className="h-4 w-36" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  if (error !== null) {
    return (
      <div aria-live="polite" className="px-4 py-4">
        <p className="text-sm text-destructive">{error}</p>
      </div>
    );
  }

  if (resolution !== null && resolution.status === "needs_confirmation") {
    return (
      <div aria-label="Confirm counterparty match" aria-live="polite" className="max-h-96 overflow-y-auto px-3 py-3" role="listbox">
        <p className="px-2 pb-1 text-xs font-medium uppercase tracking-normal text-muted-foreground">Confirm official match</p>
        <p className="px-2 pb-3 text-xs leading-5 text-muted-foreground">
          Multiple registry candidates matched "{resolution.originalInput}". Choose one before running CDD.
        </p>
        <div className="grid gap-1.5">
          {resolution.candidates.map((candidate) => (
            <button
              className="rounded-[16px] border border-transparent px-3 py-3 text-left transition hover:border-border hover:bg-muted/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              key={candidate.id}
              onClick={() => onResolutionCandidateClick(candidate)}
              role="option"
              type="button"
            >
              <span className="block text-sm font-medium text-foreground">{candidate.label}</span>
              <span className="mt-1 block text-xs text-muted-foreground">
                {candidate.sourceRegistry} · {candidate.uen ?? candidate.officialIdentifier ?? "no official identifier"} · score {candidate.score}
              </span>
              <span className="mt-1 block text-xs text-muted-foreground">{candidate.matchReason}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (suggestionStatus === "loading") {
    return (
      <div aria-live="polite" className="space-y-3 px-4 py-4">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    );
  }

  if (rankedSuggestions.length > 0) {
    return (
      <div aria-label="Official ACRA matches" aria-live="polite" className="max-h-80 overflow-y-auto px-3 py-3" role="listbox">
        <p className="px-2 pb-2 text-xs font-medium uppercase tracking-normal text-muted-foreground">Official ACRA matches</p>
        <div className="grid gap-1.5">
          {rankedSuggestions.map((suggestion) => (
            <button
              className="rounded-[16px] border border-transparent px-3 py-3 text-left transition hover:border-border hover:bg-muted/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              key={suggestion.uen}
              onClick={() => onSuggestionClick(suggestion)}
              role="option"
              type="button"
            >
              <span className="block text-sm font-medium text-foreground">{suggestion.label}</span>
              <span className="mt-1 block text-xs text-muted-foreground">{suggestion.description}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (suggestionStatus === "error") {
    return (
      <div aria-live="polite" className="px-4 py-4" title={suggestionError ?? undefined}>
        <div className="flex min-w-0 items-start gap-3 rounded-[16px] border border-border bg-muted/35 p-3">
          <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">Suggestions unavailable</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Live ACRA suggestions could not be loaded. You can still open a dossier for "{trimmedQuery}".
            </p>
          </div>
          <button
            className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-xs font-medium text-foreground shadow-sm transition hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={onRunSearch}
            type="button"
          >
            Search
            <CornerDownLeft aria-hidden="true" className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div aria-live="polite" className="px-4 py-4">
      <p className="text-sm text-muted-foreground">Press Enter to search for "{trimmedQuery}".</p>
    </div>
  );
}
