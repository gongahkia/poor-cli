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

export type WorkspaceApiAuthPolicy = {
  readonly authRequired: boolean;
  readonly production: boolean;
  readonly productionFailClosed: boolean;
  readonly explicitWorkspaceAuth: boolean;
  readonly explicitProductionLocalAuth: boolean;
  readonly oidcProtectedHttpConfigured: boolean;
  readonly message: string;
  readonly details: Readonly<Record<string, string | boolean>>;
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

const isTruthyEnv = (value: string | undefined): boolean =>
  value !== undefined && /^(1|true|yes|on)$/i.test(value.trim());

const hasText = (value: string | undefined): boolean =>
  value !== undefined && value.trim() !== "";

export const resolveWorkspaceApiAuthPolicy = (
  env: Readonly<Record<string, string | undefined>> = process.env,
): WorkspaceApiAuthPolicy => {
  const production = env["NODE_ENV"] === "production";
  const explicitWorkspaceAuth = isTruthyEnv(env["DUDE_WORKSPACE_AUTH_REQUIRED"]);
  const explicitProductionLocalAuth = isTruthyEnv(env["DUDE_ALLOW_INSECURE_PRODUCTION_LOCAL_AUTH"]);
  const httpAuthMode = env["SG_APIS_HTTP_AUTH_MODE"]?.trim().toLowerCase() ?? "";
  const oidcProtectedHttpConfigured =
    (httpAuthMode === "mixed" || httpAuthMode === "all")
    && hasText(env["SG_APIS_OIDC_ISSUER"])
    && hasText(env["SG_APIS_OIDC_AUDIENCE"]);
  const productionHasExplicitAuth =
    explicitWorkspaceAuth || explicitProductionLocalAuth || oidcProtectedHttpConfigured;
  const productionFailClosed = production && !productionHasExplicitAuth;
  const authRequired =
    explicitWorkspaceAuth
    || productionFailClosed
    || (production && oidcProtectedHttpConfigured && !explicitProductionLocalAuth);

  const message = productionFailClosed
    ? "Production REST gateway is fail-closed because no workspace auth, protected OIDC mode, or explicit local safe mode is configured."
    : explicitProductionLocalAuth
      ? "Production REST gateway local-admin fallback is explicitly enabled; use only behind private deployment controls."
      : authRequired
        ? "Workspace API auth is required for protected REST gateway routes."
        : "Local REST gateway mode allows the development local-admin fallback.";

  return {
    authRequired,
    production,
    productionFailClosed,
    explicitWorkspaceAuth,
    explicitProductionLocalAuth,
    oidcProtectedHttpConfigured,
    message,
    details: {
      authRequired,
      production,
      productionFailClosed,
      explicitWorkspaceAuth,
      explicitProductionLocalAuth,
      oidcProtectedHttpConfigured,
    },
  };
};

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
