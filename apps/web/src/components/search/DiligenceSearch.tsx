import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

export function DiligenceSearch() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [suggestionStatus, setSuggestionStatus] = useState<SuggestionStatus>("idle");
  const [suggestions, setSuggestions] = useState<ApiSearchSuggestion[]>([]);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const isSubmitting = status === "submitting";

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setSuggestionStatus("idle");
      setSuggestionError(null);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSuggestionStatus("loading");
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

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const identifier = query.trim();
    if (!identifier) {
      setStatus("error");
      setError("Enter a client or counterparty company name or UEN.");
      return;
    }

    setStatus("submitting");
    setError(null);

    try {
      navigate(`/c/${encodeURIComponent(identifier)}`);
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Navigation failed.");
    }
  };

  const handleSuggestionClick = (suggestion: ApiSearchSuggestion) => {
    setQuery(suggestion.entityName);
    navigate(`/c/${encodeURIComponent(suggestion.uen)}`);
  };

  return (
    <div className="space-y-5">
      <form className="flex flex-col gap-3 sm:flex-row" onSubmit={handleSubmit}>
        <Input
          aria-label="Client or counterparty company name or UEN"
          autoComplete="off"
          className="h-12 text-base"
          disabled={isSubmitting}
          onChange={(event) => {
            setQuery(event.target.value);
            if (status === "error") {
              setStatus("idle");
              setError(null);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="Client or counterparty company name or UEN"
          value={query}
        />
        <Button className="h-12 px-6" disabled={isSubmitting} type="submit">
          {isSubmitting ? (
            <span className="flex items-center gap-2">
              <span className="h-4 w-4 rounded-full border-2 border-primary-foreground/40 border-t-primary-foreground animate-spin" />
              Loading
            </span>
          ) : (
            "Search"
          )}
        </Button>
      </form>

      <div
        aria-live="polite"
        className="rounded-lg border border-border bg-card p-6 shadow-sm"
      >
        {isSubmitting ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-36" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : suggestionStatus === "loading" ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        ) : rankedSuggestions.length > 0 ? (
          <div>
            <p className="text-xs font-medium uppercase text-muted-foreground">Official ACRA matches</p>
            <div className="mt-3 grid gap-2">
              {rankedSuggestions.map((suggestion) => (
                <button
                  className="rounded-md border border-border p-3 text-left transition hover:bg-muted"
                  key={suggestion.uen}
                  onClick={() => handleSuggestionClick(suggestion)}
                  type="button"
                >
                  <span className="block text-sm font-medium text-foreground">{suggestion.label}</span>
                  <span className="mt-1 block text-xs text-muted-foreground">{suggestion.description}</span>
                </button>
              ))}
            </div>
          </div>
        ) : suggestionStatus === "error" ? (
          <p className="text-sm text-muted-foreground">
            {suggestionError ?? "Suggestions are temporarily unavailable."} Search still works.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">No counterparty selected.</p>
        )}
      </div>
    </div>
  );
}
