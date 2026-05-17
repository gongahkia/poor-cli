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

export type Workspace = {
  id: string;
  name: string;
  slug: string;
  createdAt: string;
};

export type WorkspaceMember = {
  id: string;
  workspaceId: string;
  displayName: string;
  email: string;
  role: WorkspaceRole;
  twoFactorEnabled: boolean;
  status: "active" | "invited" | "disabled";
};

export type WorkspaceSession = {
  workspaceId: string;
  workspaceName: string;
  actorId: string;
  actorName: string;
  actorEmail: string;
  role: WorkspaceRole;
  twoFactorVerified: boolean;
};

export type WorkspaceState = {
  workspaces: Workspace[];
  members: WorkspaceMember[];
  activeSession: WorkspaceSession;
};

const WORKSPACE_PERMISSIONS: Record<WorkspaceRole, readonly WorkspacePermission[]> = {
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

const DEFAULT_WORKSPACE_ID = "default-workspace";
const DEFAULT_MEMBER_ID = "local-admin";

export class WorkspaceAccessError extends Error {
  constructor(
    readonly code: "WORKSPACE_MISMATCH" | "WORKSPACE_PERMISSION_DENIED" | "WORKSPACE_MEMBER_DISABLED",
    message: string,
  ) {
    super(message);
    this.name = "WorkspaceAccessError";
  }
}

const nowIso = (): string => new Date().toISOString();

export const createDefaultWorkspaceState = (createdAt = nowIso()): WorkspaceState => ({
  workspaces: [{
    id: DEFAULT_WORKSPACE_ID,
    name: "Local workspace",
    slug: "local",
    createdAt,
  }],
  members: [{
    id: DEFAULT_MEMBER_ID,
    workspaceId: DEFAULT_WORKSPACE_ID,
    displayName: "Local Admin",
    email: "local-admin@dude.local",
    role: "admin",
    twoFactorEnabled: true,
    status: "active",
  }],
  activeSession: {
    workspaceId: DEFAULT_WORKSPACE_ID,
    workspaceName: "Local workspace",
    actorId: DEFAULT_MEMBER_ID,
    actorName: "Local Admin",
    actorEmail: "local-admin@dude.local",
    role: "admin",
    twoFactorVerified: true,
  },
});

export const getWorkspacePermissions = (role: WorkspaceRole): readonly WorkspacePermission[] =>
  WORKSPACE_PERMISSIONS[role];

export const canWorkspace = (
  session: WorkspaceSession,
  permission: WorkspacePermission,
  targetWorkspaceId = session.workspaceId,
): boolean =>
  session.workspaceId === targetWorkspaceId
  && WORKSPACE_PERMISSIONS[session.role].includes(permission);

export const assertWorkspaceAccess = (
  session: WorkspaceSession,
  permission: WorkspacePermission,
  targetWorkspaceId = session.workspaceId,
): void => {
  if (session.workspaceId !== targetWorkspaceId) {
    throw new WorkspaceAccessError(
      "WORKSPACE_MISMATCH",
      `Session workspace ${session.workspaceId} cannot access workspace ${targetWorkspaceId}.`,
    );
  }
  if (!WORKSPACE_PERMISSIONS[session.role].includes(permission)) {
    throw new WorkspaceAccessError(
      "WORKSPACE_PERMISSION_DENIED",
      `${session.role} cannot perform ${permission}.`,
    );
  }
};

export const isCrossWorkspaceAccessDenied = (
  session: WorkspaceSession,
  targetWorkspaceId: string,
): boolean => session.workspaceId !== targetWorkspaceId;

const WORKSPACE_STATE_KEY = "dude.workspace.state.v1";

const getBrowserStorage = (): Storage | null =>
  typeof window === "undefined" ? null : window.localStorage;

export const loadWorkspaceState = (storage: Storage | null = getBrowserStorage()): WorkspaceState => {
  if (storage === null) return createDefaultWorkspaceState();
  const raw = storage.getItem(WORKSPACE_STATE_KEY);
  if (raw === null) {
    const state = createDefaultWorkspaceState();
    storage.setItem(WORKSPACE_STATE_KEY, JSON.stringify(state));
    return state;
  }
  try {
    const parsed = JSON.parse(raw) as WorkspaceState;
    if (!Array.isArray(parsed.workspaces) || !Array.isArray(parsed.members) || parsed.activeSession === undefined) {
      throw new Error("Invalid workspace state.");
    }
    return parsed;
  } catch {
    const state = createDefaultWorkspaceState();
    storage.setItem(WORKSPACE_STATE_KEY, JSON.stringify(state));
    return state;
  }
};

export const saveWorkspaceState = (
  state: WorkspaceState,
  storage: Storage | null = getBrowserStorage(),
): void => {
  storage?.setItem(WORKSPACE_STATE_KEY, JSON.stringify(state));
};

export const resolveActiveSession = (storage: Storage | null = getBrowserStorage()): WorkspaceSession =>
  loadWorkspaceState(storage).activeSession;
