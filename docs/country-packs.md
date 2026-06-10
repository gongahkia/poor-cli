# Country-Pack Contract And Contribution Guide

Country packs extend Dude beyond Singapore without weakening the source discipline of the existing `sg_*` surface. A country pack may start as a proposal or skeleton, but it must use the same envelope contract from the first commit.

## Required Envelope

All country-pack proposals and adapters use `country-pack/v1`, implemented by `CountryPackEnvelopeSchema` in `packages/shared/src/schemas/index.ts`.

Required top-level fields:

| Field | Requirement |
| --- | --- |
| `schemaVersion` | Must be `country-pack/v1`. |
| `packId` | Lowercase ISO-3166 alpha-2 country code, such as `my`, `ph`, `id`, `th`, or `vn`. |
| `country` | Human-readable country name plus ISO-2 and ISO-3 codes. |
| `status` | One of `proposal`, `skeleton`, `public_preview`, `stable`, or `blocked`. |
| `summary` | Bounded description of what the pack does and does not cover. |
| `auth` | Whether auth is required, auth kind, environment variables, and notes. |
| `licensing` | Upstream terms URL when available, redistribution posture, commercial-use posture, attribution requirement, and notes. |
| `freshness` | Observed-at timestamp, upstream timestamp when available, refresh cadence, and stale-after threshold. |
| `publicDataLimits` | Gaps and limits that apply to the whole pack. |
| `tools` | Bounded tools exposed by the pack, each with auth and public-data-limit metadata. |
| `examples` | Fixture-backed examples, including no-match or ambiguous-match paths. |
| `contributionNotes` | Implementation notes for reviewers and future maintainers. |

## Auth, Licensing, Freshness, And Limits

Country packs must make these fields explicit before adapter code is accepted:

- `auth.required`: no silent fallback from credentialed to unauthenticated behavior.
- `auth.envVars`: all required environment variables must use the country namespace, not `SG_API_*` unless they are Singapore-specific.
- `licensing.redistribution`: use `partner_required`, `restricted`, or `unknown` when redistribution is not clearly public.
- `licensing.commercialUse`: use `partner_required`, `restricted`, or `unknown` when paid hosted use is not clearly allowed.
- `freshness.observedAt`: when the adapter or fixture was observed.
- `freshness.upstreamTimestamp`: the source's own timestamp when available.
- `publicDataLimits`: always state unsupported private, paid, ownership, or advisory scope.

## Runtime Registration Boundary

The shipped Singapore surface is registered through the SG country pack:

- `packages/mcp-server/src/country-packs/sg.ts` owns the `sg` pack metadata and tool-definition list.
- `packages/mcp-server/src/country-packs/registry.ts` exposes the pack registry.
- `packages/mcp-server/src/tools/tool-set.ts` hydrates tools from country packs and preserves the public `sg_*` contracts.

New country packs should follow this boundary rather than adding bespoke imports directly to `tool-set.ts`. A pack must define:

- namespace and country metadata;
- tool definitions exposed by that pack;
- resource URIs if the pack adds resources;
- auth environment variables or keystore boundaries;
- governance metadata for licensing, freshness, public-data limits, and owner roles.

The current SG pack is intentionally stable. Country-pack refactors must not rename `sg_*` tools, remove `sg://...` resources, or weaken the existing brief envelope semantics.

## Template

Start from [examples/country-pack-template.json](../examples/country-pack-template.json).

Validate it with:

```bash
npm run test -- packages/shared/src/__tests__/country-pack-schema.test.ts
```

## Contribution Flow

1. Open a proposal issue with country, source links, auth needs, licensing assumptions, and public-data limits.
2. Add or update a country-pack envelope fixture.
3. Add mocked tests for success, no-match, ambiguous-match, and upstream-failure behavior.
4. Add runtime registration through a country-pack module and registry entry.
5. Add adapter code only after the source terms and public-data boundaries are documented.
6. Update roadmap and licensing docs when the pack changes ASEAN expansion assumptions.

Country-pack contributions that omit provenance, freshness, gaps, limits, auth, or licensing metadata should not be merged.

## Feasibility Notes

- [ASEAN paid-data licensing assumptions](./country-packs/asean-licensing-assumptions.md)
- [ASEAN country-pack skeletons](./country-packs/asean-skeletons.md)
- [Vietnam feasibility and community-contribution path](./country-packs/vietnam-feasibility.md)
