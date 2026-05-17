# Co-Maintainer Recruitment Plan

This plan defines what it means to recruit a co-maintainer for Dude and keeps access boundaries explicit until a real person accepts. It does not grant access by itself.

## Success Definition

- Maintainer responsibilities and access boundaries are documented.
- At least three candidate co-maintainer profiles are identified.
- The blocker to adding a named co-maintainer is explicit.
- Governance docs identify the current team state and onboarding path.

## Candidate Profiles

| Profile | Why needed | First assignment | Access boundary |
| --- | --- | --- | --- |
| MCP/runtime maintainer | Reviews tool registration, resources, schemas, package entrypoints, and release automation. | Review a tool contract or country-pack registration PR. | Issue triage and PR review first; no npm/GHCR/release secrets. |
| Singapore diligence/domain maintainer | Reviews corp-services CDD workflow, evidence/gaps/provenance/freshness/limits, and public-data boundaries. | Review a dossier workflow issue or public-data limits doc. | Docs and issue review first; no production data or secrets. |
| Web/export maintainer | Reviews React UI, dossier rendering, exports, accessibility, screenshots, and frontend QA. | Review a web/export issue with Playwright evidence. | PR review first; no deployment credentials. |
| Governance/country-pack maintainer | Reviews DCO, licence posture, source licensing, country-pack envelopes, and contribution fixtures. | Review a country-pack skeleton or licensing assumption PR. | Docs/schema review first; no release authority. |

The first recruitment wave should prioritize one runtime maintainer and one domain/governance maintainer because they reduce the highest release and source-licensing risks.

## Responsibilities

Co-maintainers are expected to:

- review issues and PRs in their area within a documented response window;
- require tests or evidence proportional to risk;
- keep provenance, freshness, gaps, limits, and non-advice boundaries intact;
- avoid widening source use beyond documented licensing assumptions;
- escalate security reports through [SECURITY.md](../SECURITY.md);
- recuse themselves from commercial decisions where they have a conflict.

## Access Ladder

| Stage | Criteria | Access |
| --- | --- | --- |
| Reviewer | Two useful issue/PR reviews or one merged docs/test contribution. | GitHub triage/review only. |
| Area maintainer | Three merged contributions or repeated high-quality reviews in one area. | Repository write or maintain role scoped by owner judgment. |
| Release maintainer | Proven release discipline, packaging knowledge, and owner approval. | Release workflow access; npm/GHCR credentials remain owner-controlled until separately approved. |
| Security contact | Security-process training and owner approval. | Private security-report handling; no unilateral disclosure. |

## Outreach Shortlist

No named candidates have accepted yet. Candidate discovery should focus on:

- contributors already opening issues/PRs against MCP, Singapore data, or TypeScript runtime projects;
- Singapore civic-tech, corp-services, accounting-tech, or compliance-ops engineers who can review domain limits;
- frontend engineers with evidence-heavy workflow and export experience;
- maintainers of compatible MCP client, registry, or country-pack projects.

## Blocker

The external blocker is recruiting and receiving acceptance from at least one named person. Repo-side governance is ready enough to support that conversation, but the maintainer list must not name or imply a co-maintainer until they consent.

## First Outreach Message

```text
Hi [name],

I am looking for one or two co-maintainers for Dude, an OSS Singapore public-data MCP/runtime and CDD workflow. The highest-need areas are [runtime/domain/web/governance].

The role starts with issue/PR review only. It does not include release credentials, production secrets, or customer data. The project is strict about provenance, freshness, gaps, limits, source licensing, and non-advice boundaries.

Would you be open to reviewing one scoped issue or PR first so we can see whether the collaboration is useful?
```
