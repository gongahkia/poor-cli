import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Building2,
  Database,
  Globe2,
  KeyRound,
  Server,
  type LucideIcon,
} from "lucide-react";

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

type GatewayExplainAiReadiness = NonNullable<GatewayHealth["services"]>["analystMemo"];

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

const panelRowClasses: Record<HealthTone, string> = {
  good: "border-border bg-card text-foreground",
  warn: "border-amber-200 bg-amber-50/60 text-amber-950",
  bad: "border-destructive/30 bg-destructive/5 text-destructive",
  neutral: "border-border bg-muted/40 text-muted-foreground",
};

const statePillClasses: Record<HealthTone, string> = {
  good: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warn: "border-amber-200 bg-amber-50 text-amber-800",
  bad: "border-destructive/25 bg-destructive/10 text-destructive",
  neutral: "border-border bg-background text-muted-foreground",
};

const providerKeyEnv: Record<string, string> = {
  anthropic: "ANTHROPIC_API_KEY",
  google: "GOOGLE_API_KEY",
  openai: "OPENAI_API_KEY",
};

const providerLabels: Record<string, string> = {
  anthropic: "Anthropic",
  google: "Google",
  openai: "OpenAI",
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

function readServiceDetail(service: GatewayServiceReadiness | undefined, key: string): string | undefined {
  const value = service?.details?.[key];
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function getProviderName(service: GatewayExplainAiReadiness | undefined): string {
  return service?.provider ?? readServiceDetail(service, "provider") ?? "openai";
}

function getProviderKeyEnv(service: GatewayExplainAiReadiness | undefined): string {
  const provider = getProviderName(service);
  return readServiceDetail(service, "requiredEnvVar") ?? providerKeyEnv[provider] ?? "OPENAI_API_KEY";
}

function getExplainAiKeyLabel(service: GatewayExplainAiReadiness | undefined): string {
  const provider = getProviderName(service);
  return `${providerLabels[provider] ?? "AI provider"} explain key`;
}

function getServiceMessage(
  service: GatewayServiceReadiness | undefined,
  fallback: string,
): string {
  return service?.message ?? fallback;
}

function getServiceMetadata(service: GatewayServiceReadiness | undefined): { label: string; value: string }[] {
  return [
    formatLatency(service?.latencyMs) === null ? null : { label: "Probe", value: formatLatency(service?.latencyMs) ?? "" },
    service?.errorCode === undefined ? null : { label: "Code", value: service.errorCode },
  ].filter((item): item is { label: string; value: string } => item !== null);
}

function getExplainAiMetadata(
  service: GatewayExplainAiReadiness | undefined,
): { label: string; value: string }[] {
  const provider = getProviderName(service);
  const providerLabel = providerLabels[provider] ?? provider;
  const model = service?.model ?? readServiceDetail(service, "model") ?? "configured model";
  const latency = formatLatency(service?.latencyMs);

  return [
    ...(latency === null ? [] : [{ label: "Probe", value: latency }]),
    { label: "Provider", value: providerLabel },
    { label: "Model", value: model },
  ];
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
      fallback: "Optional web-evidence provider did not report readiness.",
      key: "tinyfish",
      label: "Optional web evidence",
      service: health.services?.tinyfish,
    },
    {
      fallback: `Set ${getProviderKeyEnv(health.services?.analystMemo)} on the REST gateway process to enable explain-only AI.`,
      key: "analystMemo",
      label: getExplainAiKeyLabel(health.services?.analystMemo),
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
  icon: Icon,
  label,
  metadata = [],
  state,
  tone,
}: {
  detail: string;
  icon?: LucideIcon;
  label: string;
  metadata?: { label: string; value: string }[];
  state: string;
  tone: HealthTone;
}) {
  return (
    <article className={cn("rounded-xl border p-3 shadow-sm", panelRowClasses[tone])}>
      <div className="flex min-w-0 items-start gap-3">
        <span className="relative mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-background">
          {Icon === undefined ? null : <Icon aria-hidden="true" className="h-4 w-4 text-muted-foreground" />}
          <span className={cn("absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-background", dotClasses[tone])} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <h3 className="min-w-0 break-words text-sm font-semibold">{label}</h3>
            <span className={cn("w-fit shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-normal", statePillClasses[tone])}>
              {state}
            </span>
          </div>
          <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">{detail}</p>
          {metadata.length > 0 ? (
            <dl className="mt-2 flex flex-wrap gap-1.5">
              {metadata.map((item) => (
                <div
                  className="inline-flex max-w-full items-baseline gap-1.5 rounded-full bg-muted/55 px-2.5 py-1"
                  key={`${item.label}-${item.value}`}
                >
                  <dt className="shrink-0 text-[10px] font-semibold uppercase tracking-normal text-muted-foreground">
                    {item.label}
                  </dt>
                  <dd className="min-w-0 break-words font-mono text-[11px] leading-4 text-foreground">{item.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
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
            {hasFailingIssue ? "Signal dependencies need attention" : "Optional evidence services need setup"}
          </p>
          <p className="mt-1 text-sm leading-6 opacity-85">
            {issues.length === 1
              ? `${primaryIssue.label}: ${primaryIssue.detail}`
              : `${issues.length} services need attention before full signal context is available.`}
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
    return <GatewayStatusPanel health={state.health} />;
  }

  return (
    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
      <StatusChip label="Gateway" service={gateway} />
      <StatusChip label="data.gov.sg" service={datagovDatastore} />
      <StatusChip label="ACRA" service={acraLookup} />
      <StatusChip label="Web evidence" service={tinyfish} />
      <StatusChip label={getExplainAiKeyLabel(analystMemo)} service={analystMemo} />
    </div>
  );
}

export function GatewayStatusPanel({ health }: { health: GatewayHealth }) {
  const uptime = formatUptime(health.runtime?.uptimeSeconds);
  const gateway = health.services?.gateway;
  const datagovDatastore = health.services?.datagovDatastore;
  const acraLookup = health.services?.acraLookup;
  const tinyfish = health.services?.tinyfish;
  const analystMemo = health.services?.analystMemo;

  return (
    <div className="space-y-3">
      <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-muted/35 p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">
            {health.readiness === "ready" ? "All checked services are ready" : "Some services need attention"}
          </p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {uptime}; {health.tools} tools enabled.
          </p>
        </div>
        <span className={cn(
          "w-fit rounded-full border px-2.5 py-1 text-xs font-semibold uppercase",
          health.readiness === "ready" ? statePillClasses.good : statePillClasses.warn,
        )}>
          {health.readiness ?? health.status}
        </span>
      </div>
      <HealthRow
        detail={getServiceMessage(gateway, "HTTP gateway is reachable.")}
        icon={Server}
        label="Gateway"
        metadata={[
          { label: "Uptime", value: uptime.replace(/^Uptime /, "") },
          { label: "Tools", value: String(health.tools) },
          ...getServiceMetadata(gateway),
        ]}
        state={health.readiness === "ready" ? "Ready" : getReadinessState(gateway?.status)}
        tone={getReadinessTone(gateway?.status)}
      />
      <HealthRow
        detail={getServiceMessage(
          datagovDatastore,
          "data.gov.sg datastore did not report readiness.",
        )}
        icon={Database}
        label="data.gov.sg datastore"
        metadata={getServiceMetadata(datagovDatastore)}
        state={getReadinessState(datagovDatastore?.status)}
        tone={getReadinessTone(datagovDatastore?.status)}
      />
      <HealthRow
        detail={getServiceMessage(acraLookup, "ACRA lookup path did not report readiness.")}
        icon={Building2}
        label="ACRA lookup"
        metadata={getServiceMetadata(acraLookup)}
        state={getReadinessState(acraLookup?.status)}
        tone={getReadinessTone(acraLookup?.status)}
      />
      <HealthRow
        detail={getServiceMessage(tinyfish, "Optional web-evidence provider did not report readiness.")}
        icon={Globe2}
        label="Optional web evidence"
        metadata={getServiceMetadata(tinyfish)}
        state={getReadinessState(tinyfish?.status)}
        tone={getReadinessTone(tinyfish?.status)}
      />
      <HealthRow
        detail={getServiceMessage(
          analystMemo,
          `Set ${getProviderKeyEnv(analystMemo)} on the REST gateway process to enable explain-only AI.`,
        )}
        icon={KeyRound}
        label={getExplainAiKeyLabel(analystMemo)}
        metadata={getExplainAiMetadata(analystMemo)}
        state={getReadinessState(analystMemo?.status)}
        tone={getReadinessTone(analystMemo?.status)}
      />
    </div>
  );
}
