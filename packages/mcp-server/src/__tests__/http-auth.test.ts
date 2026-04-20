import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { exportJWK, generateKeyPair, SignJWT } from "jose";
import { afterEach, describe, expect, it } from "vitest";
import {
  derivePublicHttpToolsets,
  HttpAuthController,
  type AuthFailure,
  type HttpAuthMode,
} from "../http-auth.js";
import type { ToolSet } from "../tools/tool-definition.js";

type TestIssuer = {
  readonly issuerUrl: URL;
  readonly audience: string;
  readonly signToken: (options?: {
    readonly scopes?: readonly string[];
    readonly scpScopes?: readonly string[];
    readonly includeScopeClaim?: boolean;
    readonly audience?: string;
    readonly issuer?: string;
    readonly expiresAt?: number | string;
  }) => Promise<string>;
  readonly setDiscoveryAvailability: (available: boolean) => void;
  readonly setJwksAvailability: (available: boolean) => void;
  readonly rotateSigningKey: () => Promise<void>;
  readonly close: () => Promise<void>;
};

const quietLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
  child: () => quietLogger,
};

const fullToolsets = new Set([
  "public",
  "briefs",
  "query",
  "health",
  "ops",
  "diligence",
  "property",
] as const satisfies readonly ToolSet[]);

const createdClosers: Array<() => Promise<void>> = [];

const createRequest = (options?: {
  readonly authorization?: string;
  readonly host?: string;
}): IncomingMessage => {
  return {
    headers: {
      ...(options?.authorization === undefined ? {} : { authorization: options.authorization }),
      ...(options?.host === undefined ? {} : { host: options.host }),
    },
  } as IncomingMessage;
};

const createOidcIssuer = async (options?: {
  readonly discoveryIssuerOverride?: string;
  readonly discoveryAvailable?: boolean;
  readonly jwksAvailable?: boolean;
}): Promise<TestIssuer> => {
  let keyVersion = 1;
  let discoveryAvailable = options?.discoveryAvailable ?? true;
  let jwksAvailable = options?.jwksAvailable ?? true;

  const createSigningMaterial = async (version: number) => {
    const keyId = `http-auth-test-key-${version}`;
    const { publicKey, privateKey } = await generateKeyPair("RS256");
    const jwk = await exportJWK(publicKey);
    return { privateKey, keyId, jwk };
  };

  let currentSigning = await createSigningMaterial(keyVersion);

  const issuerServer = createServer((req: IncomingMessage, res: ServerResponse) => {
    const address = issuerServer.address() as AddressInfo;
    const issuerUrl = `http://127.0.0.1:${address.port}`;

    if (req.url === "/.well-known/openid-configuration" || req.url === "/.well-known/oauth-authorization-server") {
      if (!discoveryAvailable) {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "discovery_unavailable" }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        issuer: options?.discoveryIssuerOverride ?? issuerUrl,
        jwks_uri: `${issuerUrl}/jwks`,
      }));
      return;
    }

    if (req.url === "/jwks") {
      if (!jwksAvailable) {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "jwks_unavailable" }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        keys: [{ ...currentSigning.jwk, kid: currentSigning.keyId, alg: "RS256", use: "sig" }],
      }));
      return;
    }

    res.writeHead(404);
    res.end();
  });

  await new Promise<void>((resolve, reject) => {
    issuerServer.once("error", reject);
    issuerServer.listen(0, "127.0.0.1", () => {
      issuerServer.off("error", reject);
      resolve();
    });
  });

  const address = issuerServer.address() as AddressInfo;
  const issuerUrl = new URL(`http://127.0.0.1:${address.port}`);
  const audience = "sg-apis-http-auth-test";

  return {
    issuerUrl,
    audience,
    signToken: async (tokenOptions) => {
      const scopes = tokenOptions?.scopes ?? [];
      const payload: Record<string, unknown> = {};
      if (tokenOptions?.includeScopeClaim !== false) {
        payload["scope"] = scopes.join(" ");
      }
      if (tokenOptions?.scpScopes !== undefined) {
        payload["scp"] = [...tokenOptions.scpScopes];
      }
      return new SignJWT(payload)
        .setProtectedHeader({ alg: "RS256", kid: currentSigning.keyId })
        .setIssuer(tokenOptions?.issuer ?? issuerUrl.href)
        .setAudience(tokenOptions?.audience ?? audience)
        .setSubject("test-user")
        .setIssuedAt()
        .setExpirationTime(tokenOptions?.expiresAt ?? "2h")
        .sign(currentSigning.privateKey);
    },
    setDiscoveryAvailability: (available: boolean) => {
      discoveryAvailable = available;
    },
    setJwksAvailability: (available: boolean) => {
      jwksAvailable = available;
    },
    rotateSigningKey: async () => {
      keyVersion += 1;
      currentSigning = await createSigningMaterial(keyVersion);
    },
    close: async () => {
      await new Promise<void>((resolve, reject) => {
        issuerServer.close((error) => {
          if (error !== undefined && error !== null) {
            reject(error);
            return;
          }
          resolve();
        });
      });
    },
  };
};

const createController = (options: {
  readonly mode: HttpAuthMode;
  readonly issuer?: string;
  readonly audience?: string;
  readonly requiredScopes?: readonly string[];
}) => {
  return new HttpAuthController({
    mode: options.mode,
    ...(options.issuer === undefined ? {} : { issuer: options.issuer }),
    ...(options.audience === undefined ? {} : { audience: options.audience }),
    requiredScopes: options.requiredScopes ?? [],
    clockSkewSec: 60,
    resourceServerUrl: new URL("http://127.0.0.1:3000/mcp"),
    fullToolsets,
    publicToolsets: derivePublicHttpToolsets(fullToolsets),
    logger: quietLogger,
  });
};

const expectAuthFailure = (value: Awaited<ReturnType<HttpAuthController["resolveInitializeSession"]>>): AuthFailure => {
  expect("statusCode" in value).toBe(true);
  return value as AuthFailure;
};

afterEach(async () => {
  while (createdClosers.length > 0) {
    const close = createdClosers.pop();
    await close?.();
  }
});

describe("HttpAuthController", () => {
  it("allows full protected access in none mode", async () => {
    const controller = createController({ mode: "none" });

    const session = await controller.resolveInitializeSession(createRequest());
    expect("statusCode" in session).toBe(false);
    if ("statusCode" in session) {
      return;
    }
    expect(session.access).toBe("protected");
    expect(session.enabledToolsets).toEqual(fullToolsets);

    const followup = await controller.authorizeSessionRequest(createRequest(), session);
    expect(followup).toBe(true);
  });

  it("limits mixed mode to the public profile without a token", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
    });

    const session = await controller.resolveInitializeSession(createRequest());
    expect("statusCode" in session).toBe(false);
    if ("statusCode" in session) {
      return;
    }
    expect(session.access).toBe("public");
    expect(session.enabledToolsets).toEqual(derivePublicHttpToolsets(fullToolsets));

    const followup = await controller.authorizeSessionRequest(createRequest(), session);
    expect(followup).toBe(true);
  });

  it("elevates mixed mode to protected when a valid bearer token is present", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const token = await issuer.signToken({ scopes: ["ops:write", "query:read"] });
    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
      requiredScopes: ["ops:write"],
    });

    const session = await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` }));
    expect("statusCode" in session).toBe(false);
    if ("statusCode" in session) {
      return;
    }
    expect(session.access).toBe("protected");
    expect(session.enabledToolsets).toEqual(fullToolsets);
    expect(session.authInfo?.subject).toBe("test-user");
    expect(session.authInfo?.scopes).toContain("ops:write");
  });

  it("rejects all mode initialization without an authorization header", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const controller = createController({
      mode: "all",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
    });

    const failure = expectAuthFailure(await controller.resolveInitializeSession(createRequest()));
    expect(failure.statusCode).toBe(401);
    expect(failure.reason).toBe("invalid_token");
    expect(failure.payload).toMatchObject({
      error: "invalid_token",
      error_description: "Missing Authorization header",
    });
  });

  it("rejects malformed authorization headers in mixed mode instead of silently downgrading", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
    });

    const failure = expectAuthFailure(
      await controller.resolveInitializeSession(createRequest({ authorization: "Basic abc123" })),
    );
    expect(failure.statusCode).toBe(401);
    expect(failure.reason).toBe("invalid_token");
    expect(failure.payload).toMatchObject({
      error: "invalid_token",
      error_description: "Malformed Authorization header. Expected 'Bearer <token>'.",
    });
  });

  it("returns insufficient_scope when required scopes are missing", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const token = await issuer.signToken({ scopes: ["ops:read"] });
    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
      requiredScopes: ["ops:write"],
    });

    const failure = expectAuthFailure(
      await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` })),
    );
    expect(failure.statusCode).toBe(403);
    expect(failure.reason).toBe("insufficient_scope");
    expect(failure.headers["WWW-Authenticate"]).toContain("scope=\"ops:write\"");
  });

  it("accepts required scopes from the scp claim array", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const token = await issuer.signToken({
      includeScopeClaim: false,
      scpScopes: ["ops:write", "query:read"],
    });
    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
      requiredScopes: ["ops:write"],
    });

    const session = await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` }));
    expect("statusCode" in session).toBe(false);
    if ("statusCode" in session) {
      return;
    }
    expect(session.access).toBe("protected");
    expect(session.authInfo?.scopes).toContain("ops:write");
  });

  it("rejects expired bearer tokens", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const token = await issuer.signToken({
      expiresAt: Math.floor(Date.now() / 1000) - 120,
    });
    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
    });

    const failure = expectAuthFailure(
      await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` })),
    );
    expect(failure.statusCode).toBe(401);
    expect(failure.reason).toBe("invalid_token");
    expect(failure.payload).toMatchObject({
      error: "invalid_token",
      error_description: "Token has expired",
    });
  });

  it("rejects tokens with an invalid audience", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const token = await issuer.signToken({ audience: "another-audience" });
    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
    });

    const failure = expectAuthFailure(
      await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` })),
    );
    expect(failure.statusCode).toBe(401);
    expect(failure.reason).toBe("invalid_token");
    expect(failure.payload).toMatchObject({
      error: "invalid_token",
    });
  });

  it("rejects initialization when oidc discovery issuer mismatches configured issuer", async () => {
    const issuer = await createOidcIssuer({
      discoveryIssuerOverride: "http://127.0.0.1/mismatched-issuer",
    });
    createdClosers.push(issuer.close);

    const token = await issuer.signToken();
    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
    });

    const failure = expectAuthFailure(
      await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` })),
    );
    expect(failure.statusCode).toBe(401);
    expect(failure.reason).toBe("invalid_token");
    expect(String(failure.payload["error_description"] ?? "")).toContain("OIDC issuer mismatch");
  });

  it("rejects malformed authorization headers for protected follow-up requests", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const token = await issuer.signToken({ scopes: ["ops:write"] });
    const controller = createController({
      mode: "all",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
      requiredScopes: ["ops:write"],
    });

    const session = await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` }));
    expect("statusCode" in session).toBe(false);
    if ("statusCode" in session) {
      return;
    }

    const followup = await controller.authorizeSessionRequest(createRequest({ authorization: "Bearer" }), session);
    expect(followup).not.toBe(true);
    const failure = followup as AuthFailure;
    expect(failure.statusCode).toBe(401);
    expect(failure.reason).toBe("invalid_token");
    expect(failure.payload).toMatchObject({
      error_description: "Malformed Authorization header. Expected 'Bearer <token>'.",
    });
  });

  it("recovers after transient oidc discovery outage without recreating the controller", async () => {
    const issuer = await createOidcIssuer({ discoveryAvailable: false });
    createdClosers.push(issuer.close);

    const token = await issuer.signToken({ scopes: ["ops:write"] });
    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
      requiredScopes: ["ops:write"],
    });

    const firstFailure = expectAuthFailure(
      await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` })),
    );
    expect(firstFailure.statusCode).toBe(401);
    expect(String(firstFailure.payload["error_description"] ?? "")).toContain("Unable to resolve jwks_uri");

    issuer.setDiscoveryAvailability(true);

    const recovered = await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${token}` }));
    expect("statusCode" in recovered).toBe(false);
    if ("statusCode" in recovered) {
      return;
    }
    expect(recovered.access).toBe("protected");
  });

  it("accepts rotated jwks keys after cache warm-up", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
    });

    const tokenV1 = await issuer.signToken({ scopes: ["query:read"] });
    const initial = await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${tokenV1}` }));
    expect("statusCode" in initial).toBe(false);
    if ("statusCode" in initial) {
      return;
    }
    expect(initial.access).toBe("protected");

    await issuer.rotateSigningKey();
    const tokenV2 = await issuer.signToken({ scopes: ["query:read"] });
    const rotated = await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${tokenV2}` }));
    expect("statusCode" in rotated).toBe(false);
    if ("statusCode" in rotated) {
      return;
    }
    expect(rotated.access).toBe("protected");
  });

  it("recovers from transient jwks endpoint outages after resolver cache refresh", async () => {
    const issuer = await createOidcIssuer();
    createdClosers.push(issuer.close);

    const controller = createController({
      mode: "mixed",
      issuer: issuer.issuerUrl.href,
      audience: issuer.audience,
    });

    const stableToken = await issuer.signToken({ scopes: ["query:read"] });
    const initial = await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${stableToken}` }));
    expect("statusCode" in initial).toBe(false);
    if ("statusCode" in initial) {
      return;
    }

    await issuer.rotateSigningKey();
    issuer.setJwksAvailability(false);
    const outageToken = await issuer.signToken({ scopes: ["query:read"] });
    const outageFailure = expectAuthFailure(
      await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${outageToken}` })),
    );
    expect(outageFailure.statusCode).toBe(401);
    expect(outageFailure.reason).toBe("invalid_token");

    issuer.setJwksAvailability(true);
    const recovered = await controller.resolveInitializeSession(createRequest({ authorization: `Bearer ${outageToken}` }));
    expect("statusCode" in recovered).toBe(false);
    if ("statusCode" in recovered) {
      return;
    }
    expect(recovered.access).toBe("protected");
  });
});
