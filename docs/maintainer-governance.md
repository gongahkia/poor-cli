# Maintainer Governance

This document defines how Dude maintainers make decisions, release changes, and handle security reports. It is operational guidance, not legal advice.

## Roles

| Role | Responsibilities |
| --- | --- |
| Project owner | Final decision authority for product scope, branding, release readiness, and high-risk legal/commercial blockers. |
| Core maintainer | Reviews MCP runtime, shared schemas, tool contracts, routing, packaging, and release automation. |
| Diligence maintainer | Reviews business dossier, CDD workflow, evidence, gaps, provenance, freshness, limits, and non-advice language. |
| Web maintainer | Reviews React UI, exports, browser smoke flows, accessibility, and user-facing copy. |
| Governance maintainer | Reviews contributor policy, release checklists, deprecation policy, source licensing notes, and security-process updates. |
| Country-pack maintainer | Reviews country-pack envelope compliance, licensing assumptions, auth boundaries, examples, and tests. |

The current owner map lives in [ownership-matrix.json](./ownership-matrix.json). Placeholder owner IDs are acceptable until named maintainers are appointed, but every release-blocking surface must have a primary and backup role.

The co-maintainer recruitment plan lives in [co-maintainer-recruitment.md](./co-maintainer-recruitment.md). Current state: no named co-maintainer has accepted yet. Until that changes, recruitment candidates must be treated as prospects, not maintainers, and no public maintainer list should imply consent.

## Access Boundaries

| Access level | Allowed before named acceptance | Requires owner approval |
| --- | --- | --- |
| Issue triage | Yes, for trusted contributors. | Removing labels, closing contentious issues, or moderating conduct. |
| PR review | Yes, as non-blocking review. | Required-reviewer status or branch protection changes. |
| Repository write | No. | Named area-maintainer appointment. |
| Release credentials | No. | Separate release-maintainer approval and packaging runbook review. |
| Security reports | No. | Security-process approval and private-report handling setup. |

Co-maintainer onboarding starts with issue/PR review and can graduate only after useful contributions, owner approval, and documented scope.

## Decision Process

- Small fixes may merge with one maintainer approval from the relevant area.
- Public contract changes require one area maintainer and one core maintainer approval.
- New data families, country packs, or paid-data integrations require documented source licensing, public-data limits, and no-match behavior before implementation approval.
- Security-sensitive, privacy-sensitive, or hosted-tier changes require governance maintainer review.
- External contributions require DCO sign-off unless a maintainer override is documented under [docs/dco.md](./dco.md).
- If maintainers disagree, the project owner decides after the tradeoff is documented in the issue or pull request.

## Release Process

1. Confirm the issue scope and definition of done.
2. Run focused tests while implementing.
3. Run `npm run verify` before a release or release-candidate branch.
4. Update docs, examples, OpenAPI/metadata artifacts, and changelog entries when the public surface changes.
5. Run the release checks in [docs/release.md](./release.md).
6. Tag and publish only after packaging smoke evidence is recorded.

Release blockers include failing tests, undocumented breaking schema changes, missing source provenance or freshness on new brief-style outputs, unreviewed licensing constraints, and unresolved security findings.

## Security Reporting Path

Security reports go through [SECURITY.md](../SECURITY.md), not public issues. The receiving maintainer should:

1. acknowledge the report within 5 business days
2. assign a severity and owner
3. create a private remediation plan
4. coordinate a patch, release note, and disclosure timing
5. update governance or public-data-limits docs if the issue changes operating assumptions

## Conduct And Enforcement

All contributors and maintainers must follow the [code of conduct](../CODE_OF_CONDUCT.md). Maintainers may moderate issues, pull requests, and discussions to keep the project focused on source-backed, bounded public-data work.
