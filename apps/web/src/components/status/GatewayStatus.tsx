import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { getGatewayJson, type GatewayHealth, type GatewayServiceReadiness } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type StatusState =
  | { status: "loading" }
  | { status: "online"; health: GatewayHealth }
  | { status: "offline"; message: string };

type GatewayStatusProps = {
  variant?: "chips" | "panel";
};

type HealthTone = "good" | "warn" | "bad" | "neutral";

export type GatewayReadinessIssue = {
  detail: string;
  key: string;
  label: string;
  state: string;
  tone: HealthTone;
};

const toneClasses: Record<HealthTone, string> = {
  good: "border-emerald-200 bg-emerald-50 text-emerald-950",
  warn: "border-amber-200 bg-amber-50 text-amber-950",
  bad: "border-destructive/30 bg-destructive/5 text-destructive",
  neutral: "border-border bg-muted text-muted-foreground",
};

const dotClasses: Record<HealthTone, string> = {
  good: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-destructive",
  neutral: "bg-muted-foreground",
};

function formatUptime(seconds: number | undefined): string {
  if (seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return "Uptime unavailable";
  }

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  const parts = [
    days > 0 ? `${days}d` : null,
    hours > 0 ? `${hours}h` : null,
    minutes > 0 ? `${minutes}m` : null,
    days === 0 && hours === 0 && minutes === 0 ? `${remainingSeconds}s` : null,
  ].filter(Boolean);

  return `Uptime ${parts.join(" ")}`;
}

function formatLatency(milliseconds: number | undefined): string | null {
  if (milliseconds === undefined || !Number.isFinite(milliseconds) || milliseconds < 0) {
    return null;
  }

  return `${Math.round(milliseconds)}ms`;
}

function getReadinessTone(status: string | undefined): HealthTone {
  if (status === "ready") return "good";
  if (status === "failing") return "bad";
  if (status === "unconfigured") return "warn";
  return "neutral";
}

function getReadinessState(status: string | undefined): string {
  if (status === "ready") return "Ready";
  if (status === "failing") return "Failing";
  if (status === "unconfigured") return "Unconfigured";
  return "Unknown";
}

function getReadinessDetail(
  service: GatewayServiceReadiness | undefined,
  fallback: string,
): string {
  const latency = formatLatency(service?.latencyMs);
  const parts = [
    service?.message ?? fallback,
    latency === null ? null : `Probe ${latency}`,
    service?.errorCode === undefined ? null : `Code ${service.errorCode}`,
  ].filter(Boolean);

  return parts.join(" ");
}

export function getGatewayReadinessIssues(health: GatewayHealth): GatewayReadinessIssue[] {
  const services = [
    {
      fallback: "data.gov.sg datastore did not report readiness.",
      key: "datagovDatastore",
      label: "data.gov.sg datastore",
      service: health.services?.datagovDatastore,
    },
    {
      fallback: "ACRA lookup path did not report readiness.",
      key: "acraLookup",
      label: "ACRA lookup",
      service: health.services?.acraLookup,
    },
    {
      fallback: "Optional web discovery did not report readiness.",
      key: "tinyfish",
      label: "TinyFish",
      service: health.services?.tinyfish,
    },
    {
      fallback: "Analyst memo provider did not report readiness.",
      key: "analystMemo",
      label: "Analyst memo",
      service: health.services?.analystMemo,
    },
  ];

  return services
    .filter(({ service }) => service?.status === "failing" || service?.status === "unconfigured")
    .map(({ fallback, key, label, service }) => ({
      detail: getReadinessDetail(service, fallback),
      key,
      label,
      state: getReadinessState(service?.status),
      tone: getReadinessTone(service?.status),
    }));
}

function HealthRow({
  detail,
  label,
  state,
  tone,
}: {
  detail: string;
  label: string;
  state: string;
  tone: HealthTone;
}) {
  return (
    <article className={cn("rounded-lg border p-3", toneClasses[tone])}>
      <div className="flex items-start gap-3">
        <span className={cn("mt-1 h-2.5 w-2.5 rounded-full", dotClasses[tone])} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
            <h3 className="text-sm font-semibold">{label}</h3>
            <p className="text-xs font-medium uppercase">{state}</p>
          </div>
          <p className="mt-1 text-xs leading-5 opacity-80">{detail}</p>
        </div>
      </div>
    </article>
  );
}

function StatusChip({
  label,
  service,
}: {
  label: string;
  service: GatewayServiceReadiness | undefined;
}) {
  const tone = getReadinessTone(service?.status);

  return (
    <span className={cn("rounded-md px-2 py-1", toneClasses[tone])}>
      {label}: {getReadinessState(service?.status)}
    </span>
  );
}

export function useGatewayHealth(): StatusState {
  const [state, setState] = useState<StatusState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    void getGatewayJson<GatewayHealth>("/api/v1/health", {}, { signal: controller.signal })
      .then((health) => {
        if (!controller.signal.aborted) {
          setState({ status: "online", health });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: "offline",
            message: error instanceof Error ? error.message : "Gateway unavailable.",
          });
        }
      });

    return () => controller.abort();
  }, []);

  return state;
}

export function GatewayReadinessBanner() {
  const state = useGatewayHealth();

  if (state.status === "loading") {
    return null;
  }

  if (state.status === "offline") {
    return (
      <aside className={cn("rounded-2xl border px-4 py-3 shadow-sm", toneClasses.bad)}>
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-semibold">Gateway unavailable</p>
            <p className="mt-1 text-sm leading-6 opacity-85">{state.message}</p>
          </div>
        </div>
      </aside>
    );
  }

  const issues = getGatewayReadinessIssues(state.health);
  if (issues.length === 0) {
    return null;
  }

  const hasFailingIssue = issues.some((issue) => issue.tone === "bad");
  const primaryIssue = issues[0];

  return (
    <aside
      className={cn(
        "rounded-2xl border px-4 py-3 shadow-sm",
        hasFailingIssue ? toneClasses.bad : toneClasses.warn,
      )}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">
            {hasFailingIssue ? "Service issue before you search" : "Optional services need setup"}
          </p>
          <p className="mt-1 text-sm leading-6 opacity-85">
            {issues.length === 1
              ? `${primaryIssue.label}: ${primaryIssue.detail}`
              : `${issues.length} services need attention before full output is available.`}
          </p>
          {issues.length > 1 ? (
            <ul className="mt-2 grid gap-1.5 text-xs leading-5 opacity-85">
              {issues.map((issue) => (
                <li
                  key={issue.key}
                  className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between"
                >
                  <span className="font-medium">{issue.label}</span>
                  <span className="sm:text-right">{issue.detail}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

export function GatewayStatus({ variant = "chips" }: GatewayStatusProps) {
  const state = useGatewayHealth();

  if (state.status === "loading") {
    return <p className="text-xs text-muted-foreground">Checking gateway uptime...</p>;
  }

  if (state.status === "offline") {
    if (variant === "panel") {
      return (
        <div className="grid gap-2">
          <HealthRow detail={state.message} label="Gateway" state="Offline" tone="bad" />
        </div>
      );
    }

    return <p className="text-xs text-destructive">Gateway offline: {state.message}</p>;
  }

  const uptime = formatUptime(state.health.runtime?.uptimeSeconds);
  const gateway = state.health.services?.gateway;
  const datagovDatastore = state.health.services?.datagovDatastore;
  const acraLookup = state.health.services?.acraLookup;
  const tinyfish = state.health.services?.tinyfish;
  const analystMemo = state.health.services?.analystMemo;

  if (variant === "panel") {
    return (
      <div className="grid gap-2">
        <HealthRow
          detail={`${getReadinessDetail(gateway, "HTTP gateway is reachable.")} ${uptime}; ${state.health.tools} tools enabled.`}
          label="Gateway"
          state={state.health.readiness === "ready" ? "Ready" : getReadinessState(gateway?.status)}
          tone={getReadinessTone(gateway?.status)}
        />
        <HealthRow
          detail={getReadinessDetail(
            datagovDatastore,
            "data.gov.sg datastore did not report readiness.",
          )}
          label="data.gov.sg datastore"
          state={getReadinessState(datagovDatastore?.status)}
          tone={getReadinessTone(datagovDatastore?.status)}
        />
        <HealthRow
          detail={getReadinessDetail(acraLookup, "ACRA lookup path did not report readiness.")}
          label="ACRA lookup"
          state={getReadinessState(acraLookup?.status)}
          tone={getReadinessTone(acraLookup?.status)}
        />
        <HealthRow
          detail={getReadinessDetail(tinyfish, "Optional web discovery did not report readiness.")}
          label="TinyFish"
          state={getReadinessState(tinyfish?.status)}
          tone={getReadinessTone(tinyfish?.status)}
        />
        <HealthRow
          detail={getReadinessDetail(
            analystMemo,
            "Analyst memo provider did not report readiness.",
          )}
          label="Analyst memo"
          state={getReadinessState(analystMemo?.status)}
          tone={getReadinessTone(analystMemo?.status)}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
      <StatusChip label="Gateway" service={gateway} />
      <StatusChip label="data.gov.sg" service={datagovDatastore} />
      <StatusChip label="ACRA" service={acraLookup} />
      <StatusChip label="TinyFish" service={tinyfish} />
      <StatusChip label="Memo" service={analystMemo} />
    </div>
  );
}
