export type WorkspaceRole = "admin" | "analyst" | "viewer";

export type WorkspacePermission =
  | "workspace:manage"
  | "member:manage"
  | "search:run"
  | "dossier:read"
  | "dossier:write"
  | "memo:generate"
  | "export:run"
  | "bulk:run"
  | "watchlist:manage"
  | "audit:read"
  | "debug:read";

export type WorkspaceApiSession = {
  readonly workspaceId: string;
  readonly actorId: string;
  readonly role: WorkspaceRole;
  readonly twoFactorVerified: boolean;
  readonly authenticated: boolean;
};

const ROLE_PERMISSIONS: Record<WorkspaceRole, readonly WorkspacePermission[]> = {
  admin: [
    "workspace:manage",
    "member:manage",
    "search:run",
    "dossier:read",
    "dossier:write",
    "memo:generate",
    "export:run",
    "bulk:run",
    "watchlist:manage",
    "audit:read",
    "debug:read",
  ],
  analyst: [
    "search:run",
    "dossier:read",
    "dossier:write",
    "memo:generate",
    "export:run",
    "bulk:run",
    "watchlist:manage",
    "audit:read",
  ],
  viewer: [
    "dossier:read",
    "export:run",
    "audit:read",
  ],
};

export class WorkspaceApiAccessError extends Error {
  readonly statusCode = 403;

  constructor(readonly code: "WORKSPACE_SESSION_REQUIRED" | "WORKSPACE_PERMISSION_DENIED", message: string) {
    super(message);
    this.name = "WorkspaceApiAccessError";
  }
}

const isWorkspaceRole = (value: string | undefined): value is WorkspaceRole =>
  value === "admin" || value === "analyst" || value === "viewer";

export const parseWorkspaceApiSession = (
  headers: { readonly get?: (name: string) => string | null } | { readonly [key: string]: string | string[] | undefined },
  options: { readonly authRequired?: boolean } = {},
): WorkspaceApiSession => {
  const getHeader = (name: string): string | undefined => {
    if (typeof headers.get === "function") return headers.get(name) ?? undefined;
    const headerRecord = headers as { readonly [key: string]: string | string[] | undefined };
    const direct = headerRecord[name.toLowerCase()] ?? headerRecord[name];
    return Array.isArray(direct) ? direct[0] : direct;
  };

  const workspaceId = getHeader("x-dude-workspace-id");
  const actorId = getHeader("x-dude-actor-id");
  const role = getHeader("x-dude-role");
  const twoFactorVerified = getHeader("x-dude-2fa-verified") === "true";

  if (workspaceId === undefined && actorId === undefined && role === undefined && options.authRequired !== true) {
    return {
      workspaceId: "default-workspace",
      actorId: "local-admin",
      role: "admin",
      twoFactorVerified: true,
      authenticated: false,
    };
  }

  if (workspaceId === undefined || actorId === undefined || !isWorkspaceRole(role)) {
    throw new WorkspaceApiAccessError(
      "WORKSPACE_SESSION_REQUIRED",
      "Workspace API requests require x-dude-workspace-id, x-dude-actor-id, and x-dude-role headers.",
    );
  }

  return {
    workspaceId,
    actorId,
    role,
    twoFactorVerified,
    authenticated: true,
  };
};

export const canWorkspaceApi = (
  session: WorkspaceApiSession,
  permission: WorkspacePermission,
): boolean => ROLE_PERMISSIONS[session.role].includes(permission);

export const assertWorkspaceApiAccess = (
  session: WorkspaceApiSession,
  permission: WorkspacePermission,
): void => {
  if (!canWorkspaceApi(session, permission)) {
    throw new WorkspaceApiAccessError(
      "WORKSPACE_PERMISSION_DENIED",
      `${session.role} cannot perform ${permission}.`,
    );
  }
};
