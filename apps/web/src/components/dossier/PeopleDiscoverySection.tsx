import { ExternalLink, Search } from "lucide-react";

import type { AgentPlanTask } from "@/components/ui/agent-plan";
import { AgentPlan } from "@/components/ui/agent-plan-loader";
import {
  getDisplaySnippet,
  getFaviconUrl,
  getSiteLabel,
} from "@/lib/external-results";
import type { PeopleDiscovery } from "@/lib/api/client";

type PeopleDiscoveryState =
  | { status: "loading" }
  | { status: "success"; discovery: PeopleDiscovery }
  | { status: "error"; message: string };

export function PeopleDiscoverySection({ state }: { state: PeopleDiscoveryState }) {
  const loadingTasks: AgentPlanTask[] = [
    {
      id: "people-follow-up",
      title: "Search people follow-up references",
      description: "Find public snippets that may identify directors, executives, or operational contacts.",
      status: "in-progress",
      priority: "medium",
      subtasks: [
        {
          id: "tinyfish-people",
          title: "Call TinyFish Search",
          description: "Searching people-oriented terms for the entity while keeping roles unverified until analyst review.",
          status: "in-progress",
          priority: "medium",
          tools: ["TinyFish Search"],
        },
        {
          id: "suggest-actions",
          title: "Prepare follow-up actions",
          description: "Turn snippets into review prompts without treating them as registry evidence.",
          status: "pending",
          priority: "medium",
          tools: ["dude-web"],
        },
      ],
    },
  ];

  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-normal text-foreground">People Follow-up</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Candidate people references from TinyFish Search; verify roles before relying on them.
          </p>
        </div>
        <Search aria-hidden="true" className="hidden h-5 w-5 shrink-0 text-muted-foreground sm:block" />
      </div>

      {state.status === "loading" ? (
        <AgentPlan
          className="mt-4"
          description="Dude is looking for public people references that can guide analyst outreach."
          tasks={loadingTasks}
          title="Dude is finding people leads"
        />
      ) : state.status === "error" ? (
        <p className="mt-4 break-words text-sm text-muted-foreground">{state.message}</p>
      ) : !state.discovery.configured ? (
        <p className="mt-4 text-sm text-muted-foreground">
          TinyFish Search is not configured on this server.
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          {state.discovery.results.length === 0 ? (
            <p className="text-sm text-muted-foreground">No people-oriented snippets were returned.</p>
          ) : (
            <div className="grid min-w-0 gap-3">
              {state.discovery.results.map((result) => {
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
                    <p className="mt-2 line-clamp-2 break-words text-sm leading-6 text-muted-foreground">
                      {getDisplaySnippet(result.snippet)}
                    </p>
                    <a
                      aria-label={`Review people result: ${result.title}`}
                      className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-foreground underline-offset-4 hover:underline"
                      href={result.url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Review result
                      <ExternalLink aria-hidden="true" className="h-3 w-3" />
                    </a>
                  </article>
                );
              })}
            </div>
          )}

          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="text-xs font-semibold uppercase text-muted-foreground">Suggested follow-up</p>
            <ul className="mt-2 space-y-1 text-sm leading-6 text-muted-foreground">
              {state.discovery.suggestedActions.map((action) => (
                <li className="break-words" key={action}>{action}</li>
              ))}
            </ul>
          </div>

          <ul className="space-y-1 text-xs leading-5 text-muted-foreground">
            {state.discovery.limits.map((limit) => (
              <li className="break-words" key={limit}>{limit}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export type { PeopleDiscoveryState };
