# Dude Cloud Entitlements And Billing Boundaries

This document defines the hosted tier boundary for Dude Cloud. It protects the open-source and self-host use cases while making paid hosted entitlements explicit before billing work starts.

## Success Definition

- OSS, self-host, and Dude Cloud tier boundaries are documented.
- Seat, workspace, usage, support, retention, and SLA entitlements have an initial product contract.
- Free upstream public sources are not paywalled; paid tiers charge for hosted workflow, collaboration, storage, assurance, and support.
- Billing, subscription, metering, and SLA implementation tasks are split into concrete follow-up backlog items.

## Principle

Dude should not charge users for access to public Singapore data that the repository already exposes through the OSS MCP runtime. Paid hosted tiers should charge for the managed application layer:

- hosted workspace identity and collaboration;
- saved dossiers, folders, exports, audit trails, and retention;
- managed bulk workflows, watchlists, and alert delivery;
- uptime, support, security posture, subprocessor evidence, and enterprise procurement work;
- optional licensed/commercial source access only when the source licence allows that hosted workflow.

If an upstream source licence prohibits paid redistribution or requires approval, the product must gate that workflow until the licence path is cleared.

## Tier Matrix

| Capability | OSS MCP | Self-host web | Dude Cloud Starter | Dude Cloud Team | Dude Cloud Partner |
| --- | --- | --- | --- | --- | --- |
| Runtime | Local stdio or self-managed HTTP MCP. | Customer-managed web + MCP deployment. | Dude-hosted web + REST + MCP. | Dude-hosted multi-user workspace. | Multi-workspace partner console for corp-services firms. |
| Public data tools | Full no-auth and customer-key `sg_*` surface. | Same as OSS, customer-managed keys. | Same public-data surface where hosted source terms permit. | Same as Starter plus team governance. | Same as Team plus client/workspace portfolio views. |
| Seats | Not applicable. | Customer-controlled. | 1 workspace owner + 2 analyst seats. | 1 owner + 10 analyst seats, additional seats billable. | 1 partner owner + configurable analyst/admin seats across client workspaces. |
| Workspaces | Local process only. | Customer-controlled. | 1 workspace. | 1 firm workspace. | Multiple client workspaces under partner account. |
| Saved dossiers | Local artifacts only if customer configures persistence. | Customer-managed persistence. | Included with default retention. | Included with folders, search, retention controls. | Included with client folders, templates, and handover exports. |
| Bulk checks | CLI/API templates. | Customer-managed. | Small CSV batches for trial workflows. | Larger queue-backed batches with audit events. | High-volume batches with partner-level reporting. |
| Watchlists/alerts | Not hosted. | Customer-managed jobs. | Not included by default. | Included with usage limits. | Included with client-level alert routing. |
| Signed exports | Available in OSS/runtime. | Customer-managed keys. | Included with hosted signing keys. | Included with retention and audit history. | Included with branded/client-ready packs. |
| Audit logs | Local trace tools only. | Customer-managed. | Workspace activity summary. | Immutable workspace audit log export. | Partner and client-workspace audit views. |
| API access | Local MCP/HTTP. | Customer-managed. | Limited hosted REST/MCP token access. | Hosted REST/MCP tokens with rate limits. | Partner API tokens with workspace scoping. |
| Support | Community/GitHub issues. | Community/GitHub issues. | Email support, no SLA. | Priority support target, incident notices. | Partner onboarding, enablement, and priority support. |
| SLA | None. | Customer-owned. | No contractual SLA. | Optional uptime target after production readiness. | Contracted only after SOC 2/MAS readiness gates. |
| Assurance packet | Public docs only. | Customer assembles evidence. | Hosted onboarding packet. | DPA, subprocessor, retention, incident, status evidence. | Partner due-diligence packet and enablement materials. |

## Entitlement Objects

The hosted product should enforce entitlements at the workspace level. Initial entitlement fields:

| Field | Meaning |
| --- | --- |
| `planId` | `starter`, `team`, `partner`, or internal beta plan. |
| `workspaceLimit` | Number of workspaces the account may create. |
| `seatLimit` | Total active human users. |
| `adminSeatLimit` | Users allowed to manage settings, billing, audit exports, and debug access. |
| `monthlyDossierLimit` | Successful dossier runs before overage or soft warning. |
| `monthlyBulkRowLimit` | CSV/bulk rows processed per calendar month. |
| `watchlistLimit` | Active watchlist entries. |
| `retentionDays` | Default saved-dossier/export retention. |
| `apiRateLimitPerMinute` | Hosted token rate limit. |
| `exportBranding` | `dude`, `workspace`, or `partner`. |
| `supportTier` | `community`, `email`, `priority`, or `partner`. |
| `slaTier` | `none`, `best_effort`, or customer-specific SLA once approved. |
| `debugLogAccess` | Whether workspace admins can view redacted backend logs in debug mode. |

Entitlement checks should be centralized server-side. Browser controls may hide disabled actions, but the REST gateway and background workers must enforce the same limits.

## Free Source Boundary

The following must remain available in OSS/self-host form under the repository licence and upstream terms:

- the stable `sg_*` tool contracts;
- no-auth public-data reads already supported by the MCP runtime;
- customer-managed API-key workflows for OneMap, URA, LTA, and similar sources;
- local brief generation and export helpers;
- documentation, schemas, prompts, and country-pack contribution surface.

Hosted Dude may restrict cloud features such as saved workspace history, managed bulk queues, hosted alerts, collaboration, audit views, support, and uptime commitments. Hosted Dude must not frame a public registry lookup itself as a proprietary paid source unless the value being sold is clearly the managed hosted workflow around that lookup.

## Source-Licensing Gates

| Source / workflow | Hosted gating rule |
| --- | --- |
| ACRA-derived enrichment | Paid hosted use stays blocked until the ACRA API Marketplace or authorised-ISP path is approved for the exact workflow. |
| OneMap | Hosted use must follow OneMap account, attribution, and commercial-use terms for the actual customer workflow. |
| URA | Hosted use must follow URA API key and redistribution controls. |
| LTA | Hosted live transport workflows require customer or Dude-held keys with permitted hosted use. |
| Optional commercial providers | Provider terms must allow hosted redistribution, storage, and customer-facing export before enablement. |
| AI memo providers | Customer must know whether memo inputs are sent to an AI provider and which provider terms apply. |

When a source gate is unresolved, the product should either disable the hosted module, require customer-managed credentials, or surface the result as a local/self-host-only capability.

## Billing Model Draft

Billing should be built around firm/workspace usage rather than per-source pricing.

Recommended first model:

- monthly or annual subscription per workspace plan;
- included seat allowance with per-seat add-ons for Team/Partner;
- included monthly dossier and bulk-row allowance with soft warnings first, then sales-assisted upgrade;
- no per-record resale of public registry data;
- optional paid onboarding/security review for enterprise or FI-adjacent buyers;
- customer-specific addendum for any SLA, data residency, subprocessor restriction, or support term.

Avoid usage-based charges before audit logs, metering, source licensing, and customer-facing usage exports are implemented.

## Required Product Backlog

| Priority | Work item | Definition of done |
| --- | --- | --- |
| P0 | Account, workspace, user, role, and invitation model. | All hosted entities carry `workspaceId`; roles enforce owner/admin/member/viewer actions. |
| P0 | Entitlement schema and server-side policy checks. | REST, MCP, exports, bulk, watchlists, and debug-log access are denied when over limit. |
| P0 | Usage event model. | Dossier runs, bulk rows, exports, API calls, watchlist evaluations, and storage are metered with request IDs. |
| P0 | Billing-safe source gates. | ACRA/OneMap/URA/LTA/commercial-provider modules can be disabled, customer-keyed, or hosted-enabled per plan. |
| P1 | Subscription checkout and invoice sync. | Plan, seats, billing period, tax metadata, and cancellation state are mirrored into Dude. |
| P1 | Customer usage page and admin warnings. | Workspace admins can see current usage, limits, and upgrade/blocking reasons. |
| P1 | Support/SLA config. | Incident notices and support routing follow plan-specific settings. |
| P2 | Partner revenue-share ledger. | Partner-attributed workspaces, revenue share, payout status, and audit records are tracked. |

## Sales Guardrails

- Do not promise hosted availability, retention, data residency, SOC 2, MAS readiness, or subprocessor restrictions beyond the current customer packet.
- Do not offer paid hosted ACRA-derived enrichment until the licensing track is cleared.
- Do not imply Dude gives legal, tax, AML, sanctions, credit, investment, or licensed compliance advice.
- Do not hide unsupported modules behind upgrade language; unsupported or unlicensed modules should say why they are unavailable.
- Do not make OSS contributors depend on a hosted account for normal local MCP usage.

## Open Decisions

- Final plan names and prices.
- Whether `Starter` is a public self-serve tier or private-beta-only.
- Whether Partner workspaces are billed to the partner firm or each end customer.
- Overage behavior: hard block, soft warning, or sales-assisted expansion.
- Which payment provider and invoice/tax workflow will be used.
- Whether any enterprise plan needs single-tenant or region-pinned deployment.

## Limits

- This document is not a price sheet or customer contract.
- It does not decide source licence compliance for any paid hosted workflow.
- It does not implement billing, subscription, metering, RBAC, or SLA enforcement by itself.
