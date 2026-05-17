import { describe, expect, it } from "vitest";

import { WorkspaceApiAccessError, assertWorkspaceApiAccess, parseWorkspaceApiSession } from "../access-control.js";

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
});
