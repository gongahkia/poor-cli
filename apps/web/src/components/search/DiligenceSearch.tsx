import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

type SearchStatus = "idle" | "submitting" | "error";

export function DiligenceSearch() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const isSubmitting = status === "submitting";

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const identifier = query.trim();
    if (!identifier) {
      setStatus("error");
      setError("Enter a company name or UEN.");
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

  return (
    <div className="space-y-5">
      <form className="flex flex-col gap-3 sm:flex-row" onSubmit={handleSubmit}>
        <Input
          aria-label="Company name or UEN"
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
          placeholder="Company name or UEN"
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
        ) : (
          <p className="text-sm text-muted-foreground">No counterparty selected.</p>
        )}
      </div>
    </div>
  );
}
