# Compliance-Use And Non-Advice Clauses

This is a product-safety mapping, not legal advice.

## Standard Clauses

Use these clauses across web, exports, docs, and API-facing artifacts:

| Clause | Standard text | Applies to |
| --- | --- | --- |
| Compliance use | Dude maps public-data evidence to operational review questions only. It is not legal, tax, credit, investment, financial, or licensed compliance advice. | Web help, PDF exports, JSON exports, CSV exports, onboarding docs. |
| PDPA and rules packs | PDPA and rules-pack references are checklist prompts for a qualified reviewer; they are not a legal opinion on whether an organisation complies with PDPA or any other law. | PDPA checklist/report work, rules-pack mapping, buyer-facing compliance docs. |
| Public-data limits | Missing public-data evidence is a gap, not proof that a counterparty is clean, approved, conflict-free, sanctioned-free, or risk-free. | Dossiers, exports, memos, watchlists, bulk results, country packs. |

The canonical web/export strings live in `apps/web/src/lib/compliance.ts`.

## Surface Review

| Surface | Current state | Required handling |
| --- | --- | --- |
| Web first-run help | Search help now states analyst-review use and excludes legal, tax, credit, and licensed compliance advice. | Keep this copy aligned with `apps/web/src/lib/compliance.ts` when adding workflow-specific help. |
| Dossier page | Dossier sections preserve `limits`, `gaps`, `provenance`, and `freshness`. | Do not hide unmatched modules or unresolved gaps. |
| Analyst memo API | Prompt and fallback memo already reject legal, tax, credit, investment, and licensed-advisor advice. | Any PDPA/rules-pack mapping must remain a checklist prompt with citations. |
| PDF export | Includes original dossier limits plus the standard compliance-use notice. | Keep `Compliance Use Notice` section in every dossier PDF export. |
| JSON export | Includes original dossier limits plus `complianceUse` notice object. | Consumers should persist this object with the exported dossier. |
| CSV export | Includes original dossier limit text plus `complianceUseNotice`. | Keep CSV disclaimer text compact enough for spreadsheet review. |
| Docs/examples | Public-data limits docs and outcome examples warn against advisory conclusions. | Link this mapping from new compliance, PDPA, and rules-pack docs. |

## Rules-Pack Mapping Boundary

Rules packs may map public evidence or missing evidence to review questions, for example:

- "Check whether a written vendor data-processing instruction exists."
- "Confirm whether a DPO has approved retention and access controls."
- "Escalate because the source did not return current licence evidence."

Rules packs must not conclude:

- "The organisation complies with PDPA."
- "The vendor is legally safe to onboard."
- "No breach, sanctions, litigation, conflict, or tax risk exists."

Any rules-pack output must keep evidence, provenance, freshness, gaps, and limits visible.
