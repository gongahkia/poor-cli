import { Building2 } from "lucide-react";
import { Link } from "react-router-dom";

import { resolveActiveSession } from "@/lib/workspace";

export function WorkspaceBadge() {
  const session = resolveActiveSession();

  return (
    <Link
      aria-label="Open workspace"
      className="inline-flex h-9 items-center gap-2 rounded-full border border-border bg-card px-3 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted"
      to="/workspace"
    >
      <Building2 className="h-4 w-4" />
      <span className="hidden sm:inline">{session.workspaceName}</span>
      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{session.role}</span>
    </Link>
  );
}
