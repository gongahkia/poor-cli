# Contributing To Dude

Thanks for helping improve Dude and Dude MCP. This repository is an evidence-first Singapore public-data runtime plus a web CDD workflow, so contributions must preserve deterministic contracts, provenance, freshness, gaps, and limits.

## Before You Start

1. Open or find an issue that describes the change.
2. State whether the change affects the MCP tool surface, web app, docs, examples, country-pack plans, or release infrastructure.
3. Keep the change scoped. Do not mix unrelated feature work, formatting churn, and generated artifacts.
4. Run the smallest useful test first, then `npm run verify` before release-sized changes.
5. Sign off commits using the project DCO policy in [docs/dco.md](./docs/dco.md).

## Local Setup

```bash
npm install
npm run build
npm run test
```

For the fastest no-credential smoke:

```bash
npm run try
```

## Contribution Rules

- Never invent Singapore data, policy values, rates, or registry facts.
- Use official public sources or existing bounded tools.
- Keep every brief-style artifact inside the shared envelope: `title`, `summary`, `evidence`, `records`, `gaps`, `provenance`, `freshness`, and `limits`.
- Do not add legal, tax, investment, credit, or licensed-advisor conclusions.
- Add source licensing and public-data-limit notes when introducing or expanding a data family.
- Add tests for schema changes, router changes, handlers, and user-visible export behavior.

## Country-Pack Contribution Workflow

Country-pack contributions must follow a stricter path because they can easily overclaim coverage or violate upstream data terms.

1. Start with a country-pack proposal issue that names the country, public surfaces, licensing assumptions, auth requirements, and unsupported private-data gaps.
2. Define the envelope fields before adding adapters. Every country pack must expose evidence, gaps, provenance, freshness, limits, and public-data-license notes.
3. Add a minimal fixture-backed skeleton first. Network calls must be mocked in tests.
4. Document authentication, rate limits, caching, redistribution constraints, and derived-output constraints.
5. Add examples that show both a successful lookup and a no-match or ambiguous-match path.
6. Update the roadmap and public-data limits docs in the same pull request.

Maintainers may reject country-pack work that lacks licensing notes, source freshness, no-match behavior, or explicit unsupported-scope language.

## Pull Request Checklist

- The issue and definition of done are linked.
- Tests or docs explain how the change was verified.
- Public contracts remain backward compatible, or the breaking change is documented and intentionally versioned.
- New user-facing text does not imply unsupported advisory conclusions.
- Generated files are reproducible from committed scripts.
- Security-sensitive changes include a review note and do not expose secrets through `VITE_` variables or logs.
- Commits include a DCO `Signed-off-by:` trailer, or the pull request documents a maintainer override.

## Related Docs

- [Country-pack contract and contribution guide](./docs/country-packs.md)
- [Maintainer governance](./docs/maintainer-governance.md)
- [DCO sign-off policy](./docs/dco.md)
- [Code of conduct](./CODE_OF_CONDUCT.md)
- [Security reporting](./SECURITY.md)
