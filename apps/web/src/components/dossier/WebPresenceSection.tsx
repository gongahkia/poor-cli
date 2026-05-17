import { ExternalLink } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import type { WebPresence } from "@/lib/api/client";

type WebPresenceState =
  | { status: "loading" }
  | { status: "success"; presence: WebPresence }
  | { status: "error"; message: string };

const TRAILING_READ_MORE_PATTERN = /\s*(?:\.{3}|…)?\s*Read more\.?$/i;

const getDisplaySnippet = (snippet: string): string => {
  const trimmed = snippet.trim();
  const cleaned = trimmed.replace(TRAILING_READ_MORE_PATTERN, "").trim();
  return cleaned || trimmed;
};

const getSiteHost = (url: string): string | null => {
  try {
    const parsed = new URL(url);
    return parsed.hostname;
  } catch {
    return null;
  }
};

const getSiteLabel = (siteName: string | null, url: string): string => siteName ?? getSiteHost(url) ?? "web";

const getFaviconUrl = (url: string): string | null => {
  const host = getSiteHost(url);
  return host === null
    ? null
    : `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`;
};

export function WebPresenceSection({ state }: { state: WebPresenceState }) {
  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <div>
        <h2 className="text-xl font-semibold tracking-normal text-foreground">Web Presence</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Web discovery, not registry evidence.
        </p>
      </div>

      {state.status === "loading" ? (
        <div className="mt-4 space-y-3">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      ) : state.status === "error" ? (
        <p className="mt-4 break-words text-sm text-muted-foreground">{state.message}</p>
      ) : !state.presence.configured ? (
        <p className="mt-4 text-sm text-muted-foreground">
          TinyFish Search is not configured on this server.
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          {state.presence.possibleOfficialWebsite !== null ? (
            <div className="min-w-0 rounded-md border border-border bg-muted/40 p-3">
              <p className="text-xs font-medium uppercase text-muted-foreground">Possible official website</p>
              <a
                className="mt-1 block max-w-full break-all text-sm font-medium text-foreground underline-offset-4 hover:underline"
                href={state.presence.possibleOfficialWebsite}
                rel="noreferrer"
                target="_blank"
              >
                {state.presence.possibleOfficialWebsite}
              </a>
            </div>
          ) : null}

          {state.presence.results.length === 0 ? (
            <p className="text-sm text-muted-foreground">No web results were returned.</p>
          ) : (
            <div className="grid min-w-0 gap-3">
              {state.presence.results.map((result) => {
                const displaySnippet = getDisplaySnippet(result.snippet);
                const siteLabel = getSiteLabel(result.siteName, result.url);
                const faviconUrl = getFaviconUrl(result.url);
                return (
                  <article className="min-w-0 rounded-md border border-border p-3" key={`${result.position}-${result.url}`}>
                    <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div className="flex min-w-0 items-start gap-2">
                        {faviconUrl === null ? null : (
                          <img
                            alt={`${siteLabel} logo`}
                            className="mt-0.5 h-6 w-6 shrink-0 rounded-sm border border-border bg-background object-contain p-0.5"
                            height="24"
                            loading="lazy"
                            onError={(event) => {
                              event.currentTarget.style.display = "none";
                            }}
                            referrerPolicy="no-referrer"
                            src={faviconUrl}
                            width="24"
                          />
                        )}
                        <a
                          className="min-w-0 break-words font-medium text-foreground underline-offset-4 hover:underline"
                          href={result.url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {result.title}
                        </a>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">{siteLabel}</span>
                    </div>
                    <p className="mt-2 line-clamp-2 break-words text-sm leading-6 text-muted-foreground">{displaySnippet}</p>
                    <a
                      aria-label={`Read more: ${result.title}`}
                      className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-foreground underline-offset-4 hover:underline"
                      href={result.url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Read more
                      <ExternalLink aria-hidden="true" className="h-3 w-3" />
                    </a>
                  </article>
                );
              })}
            </div>
          )}

          <ul className="space-y-1 text-xs leading-5 text-muted-foreground">
            {state.presence.limits.map((limit) => (
              <li className="break-words" key={limit}>{limit}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export type { WebPresenceState };
