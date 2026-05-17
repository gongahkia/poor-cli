import { useCallback, useEffect, useMemo, useState } from "react";
import { Copy, RefreshCcw, ScrollText } from "lucide-react";

import { useToast } from "@/components/notifications/ToastProvider";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { getGatewayJson, type BackendLogEntry, type DebugLogsResponse } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type LogsState =
  | { status: "checking" }
  | { status: "disabled" }
  | { status: "ready"; snapshot: DebugLogsResponse }
  | { status: "error"; message: string };

const levelClasses: Record<string, string> = {
  debug: "border-slate-200 bg-slate-50 text-slate-900",
  info: "border-blue-200 bg-blue-50 text-blue-950",
  warn: "border-amber-200 bg-amber-50 text-amber-950",
  error: "border-destructive/30 bg-destructive/5 text-destructive",
};

const readDetails = (entry: BackendLogEntry): string | null => {
  const details = { ...entry };
  delete details.ts;
  delete details.level;
  delete details.module;
  delete details.msg;
  const keys = Object.keys(details);
  if (keys.length === 0) {
    return null;
  }
  return JSON.stringify(details, null, 2);
};

const formatEntryForClipboard = (entry: BackendLogEntry): string => {
  const details = readDetails(entry);
  return [
    `[${entry.ts}] ${entry.level.toUpperCase()} ${entry.module}: ${entry.msg}`,
    details === null ? null : details,
  ].filter(Boolean).join("\n");
};

export function BackendLogsDialog() {
  const [state, setState] = useState<LogsState>({ status: "checking" });
  const [open, setOpen] = useState(false);
  const { notify } = useToast();

  const refreshLogs = useCallback(async (limit = 120) => {
    try {
      const snapshot = await getGatewayJson<DebugLogsResponse>(
        "/api/v1/debug/logs",
        { limit: String(limit) },
      );
      setState(snapshot.enabled
        ? { status: "ready", snapshot }
        : { status: "disabled" });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof Error ? error.message : "Backend debug logs are unavailable.",
      });
    }
  }, []);

  useEffect(() => {
    void refreshLogs(40);
  }, [refreshLogs]);

  const snapshot = state.status === "ready" ? state.snapshot : null;
  const entries = snapshot?.entries ?? [];
  const clipboardText = useMemo(() => entries.map(formatEntryForClipboard).join("\n\n"), [entries]);

  if (state.status === "checking" || state.status === "disabled" || state.status === "error") {
    return null;
  }

  const copyLogs = async () => {
    try {
      await navigator.clipboard.writeText(clipboardText);
      notify({ title: "Backend logs copied", description: `${entries.length} entries copied.`, tone: "success" });
    } catch {
      notify({ title: "Copy failed", description: "The browser could not write logs to the clipboard.", tone: "error" });
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (nextOpen) {
          void refreshLogs(120);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button
          aria-label="Open backend debug logs"
          className="h-9 w-9 rounded-full"
          size="icon"
          title="Backend debug logs"
          type="button"
          variant="outline"
        >
          <ScrollText className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Backend logs</DialogTitle>
          <DialogDescription>
            Local redacted gateway logs from the active debug session.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="min-w-0 break-all text-xs leading-5 text-muted-foreground">
            {snapshot?.logPath ?? "Debug log path unavailable"}
          </p>
          <div className="flex shrink-0 gap-2">
            <Button
              onClick={() => void refreshLogs(120)}
              size="sm"
              type="button"
              variant="outline"
            >
              <RefreshCcw className="mr-2 h-3.5 w-3.5" />
              Refresh
            </Button>
            <Button
              disabled={entries.length === 0}
              onClick={copyLogs}
              size="sm"
              type="button"
              variant="outline"
            >
              <Copy className="mr-2 h-3.5 w-3.5" />
              Copy
            </Button>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">
          Showing {entries.length} of {snapshot?.totalEntries ?? 0} stored entries. Observed {snapshot?.observedAt}.
        </p>

        <div className="max-h-[440px] overflow-y-auto rounded-lg border border-border bg-muted/30 p-2">
          {entries.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">No backend log entries have been stored yet.</p>
          ) : (
            <div className="grid gap-2">
              {entries.map((entry, index) => (
                <LogEntryRow entry={entry} key={`${entry.ts}-${entry.module}-${index}`} />
              ))}
            </div>
          )}
        </div>

        <ul className="space-y-1 text-xs leading-5 text-muted-foreground">
          {snapshot?.limits.map((limit) => (
            <li key={limit}>{limit}</li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

function LogEntryRow({ entry }: { entry: BackendLogEntry }) {
  const details = readDetails(entry);

  return (
    <article className={cn("rounded-md border p-3", levelClasses[entry.level] ?? levelClasses.info)}>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="break-words text-sm font-semibold">{entry.msg}</p>
          <p className="mt-1 break-all font-mono text-xs opacity-75">
            {entry.ts} · {entry.module}
          </p>
        </div>
        <span className="w-fit rounded-md bg-background/80 px-2 py-1 text-xs font-semibold uppercase">
          {entry.level}
        </span>
      </div>
      {details === null ? null : (
        <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-words rounded-md bg-background/70 p-2 text-xs leading-5">
          {details}
        </pre>
      )}
    </article>
  );
}
