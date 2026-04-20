# Audit Retention and Privacy Policy

This policy governs the local trace/request audit index used by `sg_trace_lookup` and `sg_request_lookup`.

## Scope

The local audit index stores minimal invocation metadata for correlation and incident debugging:

- `traceId`, `requestId`, `tool`, status, and timing fields
- bounded error envelope fields (`code`, `source`, retryability, optional taxonomy metadata)

The index does not persist full upstream response payloads.

## Retention Controls

Two runtime controls govern local retention:

- `SG_APIS_AUDIT_MAX_ENTRIES` (default `5000`, min `100`, max `50000`)
- `SG_APIS_AUDIT_RETENTION_SEC` (default `86400`, min `300`, max `2592000`)

Records exceeding either cap are evicted automatically.

## Operational Guidance

- Keep defaults for local debugging and short-lived traceability.
- Lower retention for constrained or shared hosts.
- Prefer explicit export to your centralized observability stack for long-term analytics; do not rely on this local index for durable compliance records.

## Privacy Boundaries

- Treat `traceId` and `requestId` as operational identifiers, not user identifiers.
- Do not attach PII to trace or request IDs.
- If host applications log user-linked identifiers, enforce redaction and retention policy in the host layer.
