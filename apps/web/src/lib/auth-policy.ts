import type { WorkspaceMember, WorkspaceRole, WorkspaceSession, WorkspaceState } from "@/lib/workspace";

export type AuthProvider = "google" | "microsoft" | "oidc" | "local";
export type TwoFactorPolicy = "optional" | "required";

export type WorkspaceAuthPolicy = {
  workspaceId: string;
  allowedProviders: AuthProvider[];
  twoFactorPolicy: TwoFactorPolicy;
  enforceForRoles: WorkspaceRole[];
};

export type LoginAttempt = {
  provider: AuthProvider;
  workspaceId: string;
  email: string;
  providerConfigured: boolean;
  secondFactorVerified: boolean;
};

export type LoginEvaluation =
  | {
      allowed: true;
      session: WorkspaceSession;
      blockers: readonly [];
    }
  | {
      allowed: false;
      session?: undefined;
      blockers: readonly string[];
    };

export const DEFAULT_AUTH_POLICY: WorkspaceAuthPolicy = {
  workspaceId: "default-workspace",
  allowedProviders: ["local", "google", "microsoft", "oidc"],
  twoFactorPolicy: "optional",
  enforceForRoles: ["admin"],
};

const findMember = (
  state: WorkspaceState,
  workspaceId: string,
  email: string,
): WorkspaceMember | undefined =>
  state.members.find((member) =>
    member.workspaceId === workspaceId
    && member.email.toLowerCase() === email.toLowerCase(),
  );

export const requiresSecondFactor = (
  policy: WorkspaceAuthPolicy,
  member: WorkspaceMember,
): boolean =>
  policy.twoFactorPolicy === "required"
  || member.twoFactorEnabled
  || policy.enforceForRoles.includes(member.role);

export const evaluateLoginAttempt = (
  state: WorkspaceState,
  policy: WorkspaceAuthPolicy,
  attempt: LoginAttempt,
): LoginEvaluation => {
  const blockers: string[] = [];
  const workspace = state.workspaces.find((item) => item.id === attempt.workspaceId);
  const member = findMember(state, attempt.workspaceId, attempt.email);

  if (workspace === undefined) blockers.push("WORKSPACE_NOT_FOUND");
  if (!policy.allowedProviders.includes(attempt.provider)) blockers.push("PROVIDER_NOT_ALLOWED");
  if (!attempt.providerConfigured) blockers.push("PROVIDER_NOT_CONFIGURED");
  if (member === undefined) blockers.push("MEMBER_NOT_FOUND");
  if (member?.status === "disabled") blockers.push("MEMBER_DISABLED");
  if (member !== undefined && requiresSecondFactor(policy, member) && !attempt.secondFactorVerified) {
    blockers.push("SECOND_FACTOR_REQUIRED");
  }

  if (blockers.length > 0 || workspace === undefined || member === undefined) {
    return { allowed: false, blockers };
  }

  return {
    allowed: true,
    blockers: [],
    session: {
      workspaceId: workspace.id,
      workspaceName: workspace.name,
      actorId: member.id,
      actorName: member.displayName,
      actorEmail: member.email,
      role: member.role,
      twoFactorVerified: attempt.secondFactorVerified,
    },
  };
};

export const SSO_CONFIGURATION_KEYS = [
  "DUDE_AUTH_GOOGLE_CLIENT_ID",
  "DUDE_AUTH_GOOGLE_CLIENT_SECRET",
  "DUDE_AUTH_MICROSOFT_CLIENT_ID",
  "DUDE_AUTH_MICROSOFT_CLIENT_SECRET",
  "DUDE_AUTH_OIDC_ISSUER",
  "DUDE_AUTH_OIDC_CLIENT_ID",
  "DUDE_AUTH_OIDC_CLIENT_SECRET",
  "DUDE_AUTH_SESSION_SECRET",
] as const;
