import { createRemoteJWKSet, jwtVerify, type JWTPayload, errors as joseErrors } from "jose";
import type { IncomingMessage } from "node:http";
import type { Logger } from "@sg-apis/shared";
import type { ToolSet } from "./tools/tool-definition.js";

export type HttpAuthMode = "none" | "mixed" | "all";

export type HttpAuthOptions = {
  readonly mode: HttpAuthMode;
  readonly issuer?: string;
  readonly audience?: string;
  readonly jwksUri?: string;
  readonly requiredScopes: readonly string[];
  readonly clockSkewSec: number;
  readonly resourceServerUrl: URL;
  readonly serviceDocumentationUrl?: URL;
  readonly fullToolsets: ReadonlySet<ToolSet>;
  readonly publicToolsets: ReadonlySet<ToolSet>;
  readonly logger: Logger;
};

export type VerifiedAccessToken = {
  readonly subject: string;
  readonly issuer: string;
  readonly audience: readonly string[];
  readonly scopes: readonly string[];
  readonly expiresAt: number | null;
  readonly claims: JWTPayload;
};

export type SessionAccess = "public" | "protected";

export type AuthorizedSession = {
  readonly access: SessionAccess;
  readonly enabledToolsets: ReadonlySet<ToolSet>;
  readonly authInfo?: VerifiedAccessToken;
};

export type AuthFailure = {
  readonly statusCode: 400 | 401 | 403;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly headers: Readonly<Record<string, string>>;
  readonly reason: string;
};

const toHeaderValue = (value: string | string[] | undefined): string | undefined => {
  return Array.isArray(value) ? value[0] : value;
};

const normalizeIssuer = (value: string): string => {
  return new URL(value).href.replace(/\/$/, "");
};

const splitScopes = (value: unknown): readonly string[] => {
  if (typeof value === "string") {
    return value.split(/\s+/).map((scope) => scope.trim()).filter((scope) => scope !== "");
  }
  if (Array.isArray(value)) {
    return value.filter((scope): scope is string => typeof scope === "string" && scope.trim() !== "");
  }
  return [];
};

const getAuthHeaderToken = (req: IncomingMessage): string | null => {
  const header = toHeaderValue(req.headers.authorization);
  if (header === undefined) {
    return null;
  }

  const [scheme, token] = header.split(/\s+/, 2);
  if (scheme?.toLowerCase() !== "bearer" || token === undefined || token.trim() === "") {
    return null;
  }
  return token;
};

const buildWwwAuthenticateHeader = (
  resourceMetadataUrl: string,
  code: "invalid_token" | "insufficient_scope",
  description: string,
  requiredScopes: readonly string[],
): string => {
  const parts = [
    `Bearer error="${code}"`,
    `error_description="${description.replaceAll("\"", "'")}"`,
    `resource_metadata="${resourceMetadataUrl}"`,
  ];

  if (requiredScopes.length > 0) {
    parts.push(`scope="${requiredScopes.join(" ")}"`);
  }

  return parts.join(", ");
};

const LOCAL_HOSTS = new Set(["127.0.0.1", "::1", "[::1]", "localhost"]);

const extractHostHeaderName = (hostHeader: string | undefined): string | null => {
  if (hostHeader === undefined || hostHeader.trim() === "") {
    return null;
  }

  const trimmed = hostHeader.trim().toLowerCase();
  if (trimmed.startsWith("[")) {
    const closing = trimmed.indexOf("]");
    return closing === -1 ? trimmed : trimmed.slice(0, closing + 1);
  }

  const [hostname] = trimmed.split(":", 1);
  return hostname ?? null;
};

const readOidcDiscovery = async (issuer: string): Promise<string> => {
  const issuerUrl = new URL(issuer);
  const normalizedIssuer = normalizeIssuer(issuer);
  const candidates = [
    new URL("/.well-known/openid-configuration", issuerUrl),
    new URL("/.well-known/oauth-authorization-server", issuerUrl),
  ];

  for (const candidate of candidates) {
    const response = await fetch(candidate);
    if (!response.ok) {
      continue;
    }

    const payload = await response.json() as Readonly<Record<string, unknown>>;
    const discoveredIssuer = typeof payload["issuer"] === "string"
      ? normalizeIssuer(payload["issuer"])
      : normalizedIssuer;
    if (discoveredIssuer !== normalizedIssuer) {
      throw new Error(`OIDC issuer mismatch. Expected ${normalizedIssuer}, got ${discoveredIssuer}.`);
    }

    const jwksUri = payload["jwks_uri"];
    if (typeof jwksUri === "string" && jwksUri.trim() !== "") {
      return jwksUri;
    }
  }

  throw new Error(`Unable to resolve jwks_uri from issuer ${issuer}.`);
};

export class HttpAuthController {
  readonly mode: HttpAuthMode;
  readonly fullToolsets: ReadonlySet<ToolSet>;
  readonly publicToolsets: ReadonlySet<ToolSet>;
  readonly requiredScopes: readonly string[];

  readonly #logger: Logger;
  readonly #issuer: string | undefined;
  readonly #audience: string | undefined;
  readonly #jwksUri: string | undefined;
  readonly #clockSkewSec: number;
  #resourceServerUrl: URL;
  #jwksResolver?: ReturnType<typeof createRemoteJWKSet>;

  constructor(options: HttpAuthOptions) {
    this.mode = options.mode;
    this.#resourceServerUrl = options.resourceServerUrl;
    this.fullToolsets = options.fullToolsets;
    this.publicToolsets = options.publicToolsets;
    this.requiredScopes = options.requiredScopes;
    this.#logger = options.logger;
    this.#issuer = options.issuer;
    this.#audience = options.audience;
    this.#jwksUri = options.jwksUri;
    this.#clockSkewSec = options.clockSkewSec;
  }

  get resourceServerUrl(): URL {
    return this.#resourceServerUrl;
  }

  setResourceServerUrl(url: URL): void {
    this.#resourceServerUrl = url;
  }

  get protectedResourceMetadataPath(): string {
    const rsPath = this.resourceServerUrl.pathname === "/" ? "" : this.resourceServerUrl.pathname;
    return `/.well-known/oauth-protected-resource${rsPath}`;
  }

  get protectedResourceMetadataUrl(): string {
    return new URL(this.protectedResourceMetadataPath, this.resourceServerUrl).href;
  }

  get protectedResourceMetadata(): Readonly<Record<string, unknown>> {
    return {
      resource: this.resourceServerUrl.href,
      authorization_servers: this.#issuer === undefined ? undefined : [this.#issuer],
      scopes_supported: this.requiredScopes.length === 0 ? undefined : this.requiredScopes,
      resource_name: "Singapore Public Data MCP",
      resource_documentation: "https://github.com/gongahkia/sg-skills",
    };
  }

  validateLocalHostHeader(req: IncomingMessage): AuthFailure | null {
    const expectedHost = this.resourceServerUrl.hostname.toLowerCase();
    if (!LOCAL_HOSTS.has(expectedHost)) {
      return null;
    }

    const hostHeader = extractHostHeaderName(toHeaderValue(req.headers.host));
    if (hostHeader !== null && LOCAL_HOSTS.has(hostHeader)) {
      return null;
    }

    return {
      statusCode: 400 as 401 | 403,
      payload: {
        error: "invalid_host_header",
        message: "Rejected request with an invalid Host header for a localhost bind.",
      },
      headers: {},
      reason: "invalid_host_header",
    };
  }

  async resolveInitializeSession(req: IncomingMessage): Promise<AuthorizedSession | AuthFailure> {
    if (this.mode === "none") {
      return {
        access: "protected",
        enabledToolsets: this.fullToolsets,
      };
    }

    const token = getAuthHeaderToken(req);
    if (token === null) {
      if (this.mode === "all") {
        return this.buildInvalidTokenFailure("Missing Authorization header");
      }
      return {
        access: "public",
        enabledToolsets: this.publicToolsets,
      };
    }

    const authInfo = await this.verifyAccessToken(token).catch((error) => this.toAuthFailure(error));
    if ("statusCode" in authInfo) {
      return authInfo;
    }

    return {
      access: "protected",
      enabledToolsets: this.fullToolsets,
      authInfo,
    };
  }

  async authorizeSessionRequest(
    req: IncomingMessage,
    session: AuthorizedSession,
  ): Promise<true | AuthFailure> {
    if (this.mode === "none" || session.access === "public") {
      return true;
    }

    const token = getAuthHeaderToken(req);
    if (token === null) {
      return this.buildInvalidTokenFailure("Missing Authorization header");
    }

    const authInfo = await this.verifyAccessToken(token).catch((error) => this.toAuthFailure(error));
    if ("statusCode" in authInfo) {
      return authInfo;
    }

    return true;
  }

  private async getJwksResolver() {
    if (this.#issuer === undefined || this.#audience === undefined) {
      throw new Error("OIDC issuer and audience must be configured for protected HTTP auth.");
    }

    if (this.#jwksResolver !== undefined) {
      return this.#jwksResolver;
    }

    const jwksUri = this.#jwksUri ?? await readOidcDiscovery(this.#issuer);
    this.#jwksResolver = createRemoteJWKSet(new URL(jwksUri));
    return this.#jwksResolver;
  }

  private async verifyAccessToken(token: string): Promise<VerifiedAccessToken> {
    const issuer = this.#issuer;
    const audience = this.#audience;
    if (issuer === undefined || audience === undefined) {
      throw new Error("OIDC issuer and audience must be configured for protected HTTP auth.");
    }

    const jwks = await this.getJwksResolver();
    const verification = await jwtVerify(token, jwks, {
      issuer,
      audience,
      clockTolerance: this.#clockSkewSec,
    });

    const scopes = Array.from(new Set([
      ...splitScopes(verification.payload["scope"]),
      ...splitScopes(verification.payload["scp"]),
    ]));

    if (this.requiredScopes.length > 0 && !this.requiredScopes.every((scope) => scopes.includes(scope))) {
      return Promise.reject(new Error("Insufficient scope"));
    }

    return {
      subject: typeof verification.payload.sub === "string" ? verification.payload.sub : "unknown",
      issuer: typeof verification.payload.iss === "string" ? verification.payload.iss : issuer,
      audience: Array.isArray(verification.payload.aud)
        ? verification.payload.aud.filter((value): value is string => typeof value === "string")
        : typeof verification.payload.aud === "string"
          ? [verification.payload.aud]
          : [audience],
      scopes,
      expiresAt: typeof verification.payload.exp === "number" ? verification.payload.exp : null,
      claims: verification.payload,
    };
  }

  private buildInvalidTokenFailure(description: string): AuthFailure {
    return {
      statusCode: 401,
      payload: {
        error: "invalid_token",
        error_description: description,
      },
      headers: {
        "WWW-Authenticate": buildWwwAuthenticateHeader(
          this.protectedResourceMetadataUrl,
          "invalid_token",
          description,
          this.requiredScopes,
        ),
      },
      reason: "invalid_token",
    };
  }

  private toAuthFailure(error: unknown): AuthFailure {
    if (error instanceof Error && error.message === "Insufficient scope") {
      return {
        statusCode: 403,
        payload: {
          error: "insufficient_scope",
          error_description: error.message,
        },
        headers: {
          "WWW-Authenticate": buildWwwAuthenticateHeader(
            this.protectedResourceMetadataUrl,
            "insufficient_scope",
            error.message,
            this.requiredScopes,
          ),
        },
        reason: "insufficient_scope",
      };
    }

    if (error instanceof joseErrors.JWTExpired) {
      return this.buildInvalidTokenFailure("Token has expired");
    }

    if (error instanceof joseErrors.JWSSignatureVerificationFailed
      || error instanceof joseErrors.JWTClaimValidationFailed
      || error instanceof joseErrors.JWKSMultipleMatchingKeys
      || error instanceof joseErrors.JOSENotSupported
      || error instanceof joseErrors.JWTInvalid) {
      return this.buildInvalidTokenFailure(error.message);
    }

    this.#logger.warn("OIDC token verification failed", {
      error: error instanceof Error ? error.message : String(error),
    });
    return this.buildInvalidTokenFailure(
      error instanceof Error ? error.message : "Unable to validate access token",
    );
  }
}

export const derivePublicHttpToolsets = (
  fullToolsets: ReadonlySet<ToolSet>,
): ReadonlySet<ToolSet> => {
  const visible = ["public", "briefs", "query", "health", "diligence", "property"] as const satisfies readonly ToolSet[];
  return new Set(visible.filter((toolset) => fullToolsets.has(toolset)));
};
