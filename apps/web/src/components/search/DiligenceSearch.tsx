import { FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, CornerDownLeft } from "lucide-react";

import { useToast } from "@/components/notifications/ToastProvider";
import { AiInput } from "@/components/ui/ai-input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getGatewayJson,
  type ApiSearchSuggestion,
} from "@/lib/api/client";
import { rankSearchSuggestions } from "@/lib/search/rank-search-suggestions";

type SearchStatus = "idle" | "submitting" | "error";
type SuggestionStatus = "idle" | "loading" | "ready" | "error";

type SuggestionResponse = {
  query: string;
  suggestions: ApiSearchSuggestion[];
  warning?: string;
};

type DiligenceSearchProps = {
  secondaryAction?: ReactNode;
};

export function DiligenceSearch({ secondaryAction }: DiligenceSearchProps = {}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [suggestionStatus, setSuggestionStatus] = useState<SuggestionStatus>("idle");
  const [suggestions, setSuggestions] = useState<ApiSearchSuggestion[]>([]);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { notify } = useToast();
  const isSubmitting = status === "submitting";
  const trimmedQuery = query.trim();
  const canLookupSuggestions = trimmedQuery.length >= 2;

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
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
  }, [query]);

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

  const runSearch = () => {
    const identifier = trimmedQuery;
    if (!identifier) {
      setStatus("error");
      setError("Enter a client or counterparty company name or UEN.");
      notify({
        title: "Search needs an identifier",
        description: "Enter a Singapore company name or UEN before opening a dossier.",
        tone: "warning",
      });
      return;
    }

    setStatus("submitting");
    setError(null);

    try {
      navigate(`/c/${encodeURIComponent(identifier)}`);
    } catch (err) {
      setStatus("error");
      const message = err instanceof Error ? err.message : "Navigation failed.";
      setError(message);
      notify({ title: "Search failed", description: message, tone: "error" });
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    runSearch();
  };

  const shouldShowSearchPanel = isSubmitting || error !== null || canLookupSuggestions || suggestionStatus !== "idle";

  const handleSuggestionClick = (suggestion: ApiSearchSuggestion) => {
    setQuery(suggestion.entityName);
    navigate(`/c/${encodeURIComponent(suggestion.uen)}`);
  };

  const dropdownContent = shouldShowSearchPanel ? (
    <SearchDropdownContent
      error={error}
      isSubmitting={isSubmitting}
      onRunSearch={runSearch}
      onSuggestionClick={handleSuggestionClick}
      rankedSuggestions={rankedSuggestions}
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
          onSubmit={runSearch}
          onValueChange={(nextQuery) => {
            setQuery(nextQuery);
            if (status === "error") {
              setStatus("idle");
              setError(null);
            }
          }}
          placeholder="Company name or UEN"
          secondaryAction={secondaryAction}
          value={query}
        />
      </form>
    </div>
  );
}

function SearchDropdownContent({
  error,
  isSubmitting,
  onRunSearch,
  onSuggestionClick,
  rankedSuggestions,
  suggestionError,
  suggestionStatus,
  trimmedQuery,
}: {
  error: string | null;
  isSubmitting: boolean;
  onRunSearch: () => void;
  onSuggestionClick: (suggestion: ApiSearchSuggestion) => void;
  rankedSuggestions: ApiSearchSuggestion[];
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
