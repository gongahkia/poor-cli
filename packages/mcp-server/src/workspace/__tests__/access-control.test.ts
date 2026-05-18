import { describe, expect, it } from "vitest";

import {
  WorkspaceApiAccessError,
  assertWorkspaceApiAccess,
  parseWorkspaceApiSession,
  resolveWorkspaceApiAuthPolicy,
} from "../access-control.js";

describe("workspace API access control", () => {
  it("allows self-host local mode without headers when auth is not required", () => {
    const session = parseWorkspaceApiSession({});
    expect(session).toMatchObject({
      workspaceId: "default-workspace",
      role: "admin",
      authenticated: false,
    });
    expect(() => assertWorkspaceApiAccess(session, "bulk:run")).not.toThrow();
  });

  it("enforces headers and role permissions for hosted mode", () => {
    expect(() => parseWorkspaceApiSession({}, { authRequired: true })).toThrow(WorkspaceApiAccessError);

    const viewer = parseWorkspaceApiSession({
      "x-dude-workspace-id": "workspace-a",
      "x-dude-actor-id": "viewer-a",
      "x-dude-role": "viewer",
      "x-dude-2fa-verified": "true",
    }, { authRequired: true });

    expect(() => assertWorkspaceApiAccess(viewer, "dossier:read")).not.toThrow();
    expect(() => assertWorkspaceApiAccess(viewer, "bulk:run")).toThrow("viewer cannot perform bulk:run");
  });

  it("keeps local defaults usable while production fails closed without explicit auth", () => {
    const development = resolveWorkspaceApiAuthPolicy({});
    expect(development).toMatchObject({
      authRequired: false,
      production: false,
      productionFailClosed: false,
    });
    expect(parseWorkspaceApiSession({}, { authRequired: development.authRequired })).toMatchObject({
      actorId: "local-admin",
      authenticated: false,
    });

    const production = resolveWorkspaceApiAuthPolicy({ NODE_ENV: "production" });
    expect(production).toMatchObject({
      authRequired: true,
      production: true,
      productionFailClosed: true,
    });
    expect(() => parseWorkspaceApiSession({}, { authRequired: production.authRequired }))
      .toThrow(WorkspaceApiAccessError);
  });

  it("allows an explicit production local safe mode but does not enable it implicitly", () => {
    const policy = resolveWorkspaceApiAuthPolicy({
      DUDE_ALLOW_INSECURE_PRODUCTION_LOCAL_AUTH: "true",
      NODE_ENV: "production",
    });

    expect(policy).toMatchObject({
      authRequired: false,
      explicitProductionLocalAuth: true,
      production: true,
      productionFailClosed: false,
    });
  });
});
