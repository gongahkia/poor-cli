# External Diligence Adapters

This is the implementation contract for issues #52, #53, #54, and #55.

## OpenSanctions

`sg_sanctions_screen` screens a company name and optional UEN against OpenSanctions candidate matches. It returns the standard brief envelope with candidate records, risk flags, provenance, freshness, gaps, and limits.

Operational rules:

- Requires `OPENSANCTIONS_API_KEY`.
- Returns `OPENSANCTIONS_API_KEY_REQUIRED` when credentials or commercial licensing are not configured.
- Exact and fuzzy matches are candidate hits only; analysts must review before treating them as true sanctions results.

Reference: [OpenSanctions API docs](https://www.opensanctions.org/docs/api/).

## OpenCorporates

`sg_opencorporates_links` links a Singapore entity to OpenCorporates company candidates.

Operational rules:

- Requires `OPENCORPORATES_API_TOKEN`.
- Uses `jurisdiction_code=sg` by default.
- Never infers ownership, control, UBOs, or corporate relationships from cross-links.

References: [OpenCorporates API documentation](https://knowledge.opencorporates.com/knowledge-base/api-documentation/) and [authentication documentation](https://knowledge.opencorporates.com/knowledge-base/api-authentication-authorisation/).

## Adverse Media Lite

`sg_adverse_media_lite` searches bounded official Singapore public feeds such as SFA, NEA, MPA, and URA.

Operational rules:

- No general web crawling.
- No sentiment, culpability, or adverse-event NLP inference.
- Confidence means official-feed keyword occurrence only.

## Relationship Graph

`sg_relationship_graph` builds a shallow graph from supplied dossier records.

Permitted edges:

- registered address from ACRA fields
- shared registered address heuristic
- normalized name-family heuristic

Explicitly not supported:

- directors/officers
- shareholders
- UBOs
- subsidiaries or parent entities
- ownership or control claims

Business dossiers can include external diligence by setting `includeExternalDiligence: true`; otherwise the direct tools remain explicit follow-ups in `nextChecks`.
