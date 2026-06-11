# Haus Future Evaluations

These notes close the P3 future-evaluation backlog without promoting deferred
ideas into the product roadmap. Each section states the current decision,
repository evidence, and gates that must be satisfied before the idea can move
from future evaluation to implementation.

Evaluation date: 2026-06-11.

## Real-time Collaborative Project Sharing

Decision: defer.

Haus should not add real-time collaborative project sharing yet. The current
product is intentionally local-first and single-user: project save/load,
autosave, scenario duplication, validation snapshots, and static exports are
already useful without introducing accounts, permissions, or live state
reconciliation. Adding concurrent editing now would create data-loss and trust
risks around floor-plan edits, renovation assumptions, accessibility warnings,
and client-facing exports.

Current evidence:

- Local project state is persisted through `viewer/js/project.js` using
  autosave, project JSON export/import, scenario history, and validation
  snapshots.
- Server-side project tools in `src/haus/mcp_server.py` cover create, list,
  load, save, duplicate scenario, and export report flows against local runtime
  files.
- `tests/test_workbench.py` and `tests/test_mcp_server.py` cover local project
  model migration, project scenario operations, validation snapshots, and report
  export.
- The README and product boundaries position Haus around local-first exports,
  not shared cloud workspaces.

Why it remains P3:

- There is no identity, invitation, role, or permission model.
- There is no optimistic-locking or merge strategy for concurrent object edits,
  room tracing, calibration changes, scenario application, or destructive
  mutations.
- There is no audit trail that distinguishes user edits, deterministic planner
  edits, provider-reviewed edits, and external collaborator edits.
- Client-safe report output would need share-state redaction rules before a
  designer or homeowner could safely invite another party.

Promotion gates:

- Add a project revision identifier to every saved project mutation and reject
  stale writes with a user-visible recovery path.
- Define roles for owner, editor, commenter, and viewer, including which roles
  can apply scenarios, export reports, send data to providers, or change privacy
  settings.
- Add a conflict UI for calibration, geometry, product, assumption, and report
  edits rather than silently accepting last-write-wins changes.
- Add a durable audit log that records actor, timestamp, operation, affected
  object IDs, and before/after summary.
- Add two-session tests that prove simultaneous edits cannot lose project data
  and that exported reports reflect the intended revision.

Acceptable first experiment:

- Asynchronous review links for static HTML reports or zipped project bundles.
  These preserve the local-first model while testing whether users actually need
  collaborative review before Haus takes on live multi-user editing.

## Cloud Storage

Decision: defer.

Haus should not add first-party cloud storage until its local privacy contract,
project bundle export, and recovery paths have been exercised by real users.
Floor plans can expose addresses, household routines, mobility needs, budgets,
and client identities. A hosted storage feature would make Haus responsible for
custody, access control, retention, deletion, breach response, regional hosting,
and support for users who believe their plans are private.

Current evidence:

- The editor states that floor plans stay on the user's machine unless an
  external provider, web search, or export is used.
- `viewer/js/project.js` stores local project state, exports standalone project
  JSON, and imports Haus project files without requiring a hosted account.
- `src/haus/workbench.py` exports project bundles containing layout JSON,
  project JSON, reports, screenshots, source images, and catalog cache files.
- `tests/test_workbench.py` verifies bundle contents and client path redaction
  for report output.
- The chat server includes privacy settings that can disable web search and API
  key storage.

Why it remains P3:

- There is no data classification for plan images, source file paths, household
  accessibility data, client details, catalog URLs, or provider prompts.
- There is no cloud account, authentication, password reset, session management,
  storage-region, retention, deletion, or export/delete-all flow.
- There is no encryption key strategy, backup policy, or incident-response
  story.
- Cloud sync would need the same revision and conflict model as collaborative
  editing, because local autosave and cloud save can race.

Promotion gates:

- Publish a data inventory covering every field stored in a project bundle,
  every field sent to providers, and every field shown in client-facing reports.
- Add explicit consent screens for cloud upload, source-image retention,
  provider use, and report sharing.
- Define encryption at rest, encryption in transit, key ownership, backup
  retention, deletion guarantees, and account recovery limits.
- Add export-all and delete-all flows that work for projects, source images,
  generated reports, catalog cache, and provider metadata.
- Add sync tests for offline edits, stale cloud revisions, failed uploads,
  corrupt remote data, and project bundle round-trips.

Acceptable first experiment:

- A documented "bring your own storage" workflow that saves and loads Haus
  project bundles from a user-controlled folder. This can validate demand for
  cross-device continuity without making Haus the system of record.
