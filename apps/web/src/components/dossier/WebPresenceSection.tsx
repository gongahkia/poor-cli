import { Skeleton } from "@/components/ui/skeleton";
import type { WebPresence } from "@/lib/api/client";

type WebPresenceState =
  | { status: "loading" }
  | { status: "success"; presence: WebPresence }
  | { status: "error"; message: string };

export function WebPresenceSection({ state }: { state: WebPresenceState }) {
  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
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
        <p className="mt-4 text-sm text-muted-foreground">{state.message}</p>
      ) : !state.presence.configured ? (
        <p className="mt-4 text-sm text-muted-foreground">
          TinyFish Search is not configured on this server.
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          {state.presence.possibleOfficialWebsite !== null ? (
            <div className="rounded-md border border-border bg-muted/40 p-3">
              <p className="text-xs font-medium uppercase text-muted-foreground">Possible official website</p>
              <a
                className="mt-1 block truncate text-sm font-medium text-foreground underline-offset-4 hover:underline"
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
            <div className="grid gap-3">
              {state.presence.results.map((result) => (
                <article className="rounded-md border border-border p-3" key={`${result.position}-${result.url}`}>
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                    <a
                      className="font-medium text-foreground underline-offset-4 hover:underline"
                      href={result.url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {result.title}
                    </a>
                    <span className="text-xs text-muted-foreground">{result.siteName ?? "web"}</span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{result.snippet}</p>
                </article>
              ))}
            </div>
          )}

          <ul className="space-y-1 text-xs leading-5 text-muted-foreground">
            {state.presence.limits.map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export type { WebPresenceState };
