# GitHub Project Roadmap Setup

This document defines the public GitHub Projects board that should mirror the pivot backlog. The board itself could not be created from this checkout because the current `gh` token does not include the GitHub Projects scope.

Observed blocker on 2026-05-17:

```text
gh project list --owner gongahkia --format json --limit 20
GraphQL: Resource not accessible by integration (viewer.organization.login)
```

## Success Definition

- Roadmap conventions are documented in-repo.
- Board fields and views are specified before creation.
- Existing roadmap/task labels map cleanly to board fields.
- Good-first-issue candidates have a repeatable labeling rule.
- Actual board creation is tracked as a follow-up requiring GitHub Projects permissions.

## Board

Name: `Dude Pivot Roadmap`

Visibility: public, attached to `gongahkia/dude`.

Purpose: one board for roadmap issues, concrete implementation tasks, external blockers, and follow-up issues created when repo-side work is complete but third-party action remains.

## Fields

| Field | Type | Values |
| --- | --- | --- |
| Priority | single select | `p0`, `p1`, `p2` |
| Kind | single select | `roadmap`, `task`, `external-blocker`, `docs`, `bug`, `feature` |
| Area | single select | `docs`, `distribution`, `platform`, `country-pack`, `gateway`, `ops`, `web`, `diligence`, `compliance` |
| Status | single select | `Inbox`, `Ready`, `In progress`, `Blocked external`, `Review`, `Done` |
| Target window | single select | `Now`, `Next`, `Later`, `Moved out of 90-day plan` |
| External dependency | text | Required when status is `Blocked external`. |

## Views

| View | Filter/grouping | Use |
| --- | --- | --- |
| Now | `Status != Done`, grouped by `Priority` | Weekly execution queue. |
| External blockers | `Status = Blocked external` | Follow-up list for submissions, permissions, outreach, and third-party reviews. |
| By area | grouped by `Area` | Maintainer ownership and review planning. |
| Roadmaps | `kind:roadmap` | Parent tracking issues and phase-level progress. |
| Good first issues | `good first issue`, `Status != Done` | Contributor onboarding queue. |

## Label Mapping

| GitHub label | Project field |
| --- | --- |
| `priority:p0`, `priority:p1`, `priority:p2` | Priority |
| `kind:roadmap`, `kind:task` | Kind |
| `area:*` | Area |
| `good first issue` | Good first issues view |
| `blocked` or follow-up title containing `External blocker` | `Status = Blocked external` |

## Good-First-Issue Rule

Apply `good first issue` only when the issue:

- is docs, examples, metadata, or a narrowly mocked test;
- has a single obvious file or folder owner;
- does not require secrets, source licensing decisions, third-party acceptance, or production credentials;
- includes a definition of done that a contributor can verify locally.

Good candidates in this repo usually include docs parity, example fixtures, country-pack skeleton metadata, compatibility-matrix updates, and no-auth smoke improvements.

## Creation Steps

1. Re-authenticate `gh` with GitHub Projects permissions, or use the GitHub web UI with an owner account.
2. Create `Dude Pivot Roadmap`.
3. Add all open `priority:*`, `kind:*`, and `area:*` issues.
4. Create the views above.
5. Set external follow-up issues to `Blocked external`.
6. Add the public project URL to this document.

Public project URL: TBD.
