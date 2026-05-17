import { Building2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { resolveActiveSession } from "@/lib/workspace";
import { WorkspacePanel } from "@/pages/WorkspacePage";

export function WorkspaceBadge() {
  const session = resolveActiveSession();

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          aria-label="Open workspace"
          className="inline-flex h-9 items-center gap-2 rounded-full border border-border bg-card px-3 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted"
          type="button"
        >
          <Building2 className="h-4 w-4" />
          <span className="hidden sm:inline">{session.workspaceName}</span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{session.role}</span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-6xl overflow-y-auto rounded-[28px] border-border bg-background p-1 shadow-2xl">
        <DialogTitle className="sr-only">{session.workspaceName}</DialogTitle>
        <DialogDescription className="sr-only">
          Persisted dossiers, watchlists, bulk jobs, and audit events for this workspace.
        </DialogDescription>
        <div className="rounded-[24px] bg-muted/35 p-5 sm:p-6">
          <WorkspacePanel />
        </div>
      </DialogContent>
    </Dialog>
  );
}
