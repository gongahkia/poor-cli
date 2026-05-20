# Public Data Limits

Dude uses Singapore public registry and public-data sources. Treat missing private corporate data as a coverage limit, not as evidence that no relationship exists.

## What Dude Does Not Infer

- Directors, officers, shareholders, beneficial owners, subsidiaries, parent entities, and control relationships.
- Corporate control graphs or related-party networks.
- Creditworthiness, financial strength, sanctions, litigation, legal exposure, tax positions, or investment suitability.
- Private data from paid corporate registries, bank KYC files, internal procurement systems, or non-public filings.

`sg_relationship_graph` may preserve explicit source-declared relationship edges if they are supplied in dossier records. Those edges are supplemental evidence for analyst review; Dude still does not infer the relationship from names, addresses, missing data, or graph shape.

## How To Read Missing Ownership Evidence

If a dossier does not show shareholders or a corporate graph, the correct interpretation is:

> The selected public sources do not expose ownership/control evidence through this workflow.

It is not:

> The company has no owners, related parties, subsidiaries, or control risks.

## Where This Is Enforced

- `sg_business_dossier` includes a `NO_CORPORATE_GRAPH` limit in the returned limits envelope.
- `/api/v1/dude/memo` instructs the AI provider not to add ownership, director, shareholder, or control claims unless present in the dossier.
- The web dossier page and structured exports carry the original `limits`, `gaps`, `provenance`, and `freshness` fields forward, plus standard compliance-use and non-advice clauses.

## Example

If ACRA identity matches but GeBIZ returns no awards and no ownership registry exists in the dossier:

- Safe: "ACRA identity matched; GeBIZ returned no public award records in this run; ownership/control evidence is outside this public-data workflow."
- Unsafe: "The counterparty has no related-party or ownership concerns."
