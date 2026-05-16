# License Strategy

This is a product and governance decision record, not legal advice.

## Current Decision

Keep Dude and Dude MCP under the current MIT licence for now.

No licence-change follow-up issue is needed at this stage because the hosted-tier boundaries, neutral-home path, and paid-data licensing model are not mature enough to justify migration cost.

## Decision Criteria

Revisit the licence only if one of these triggers becomes true:

- a neutral foundation or fiscal host asks for a different inbound or outbound licence
- enterprise adopters block adoption specifically because MIT lacks patent language
- the project introduces a real open-core split where hosted-only code must be separated from the OSS runtime
- a paid-data partner requires tighter redistribution boundaries for partner-specific adapters
- contributors or co-maintainers need a formal relicensing vote before accepting substantial new work

## Option Comparison

| Option | Hosted-tier fit | Enterprise adoption | Contributor impact | Data-licensing impact | Current recommendation |
| --- | --- | --- | --- | --- | --- |
| MIT | Simple for self-host, SDK, examples, and MCP runtime reuse. Hosted value can still come from accounts, workflow storage, support, SLAs, and managed operations. | Familiar and permissive, but does not include Apache-style express patent language. | Lowest friction. Existing contributors already participate under MIT. | Does not solve upstream ACRA, URA, OneMap, or ASEAN paid-data constraints; those need separate source terms. | Keep. |
| Apache-2.0 | Also compatible with open-source runtime and hosted services. Patent language may help enterprise procurement. | Often preferred by larger enterprise legal teams because patent grant and contribution terms are clearer. | Requires relicensing review and contributor agreement from prior contributors or a clean legal path. | Still does not permit redistribution of restricted upstream data. | Revisit if enterprise buyers ask for patent coverage. |
| BSL-to-Apache | Can protect a future hosted/open-core commercial moat while promising delayed open release. | Some enterprises accept it; many OSS ecosystems treat current BSL code as source-available rather than open source. | Highest friction. Country-pack and community contributors may avoid source-available terms. Requires careful separation of code that remains truly OSS. | Still cannot override upstream data licences. Could confuse users into thinking source-available code permits paid data reuse. | Do not adopt now. |

## Hosted-Tier Implications

MIT remains compatible with a hosted tier as long as the paid value is clearly in hosted workflow capabilities rather than paywalled public upstream data:

- workspace accounts, RBAC, and audit logs
- persistent dossier folders and export manifests
- managed uptime, support, backups, and incident response
- watchlists, bulk workflow persistence, and notifications
- buyer-facing compliance packs and operational evidence

The hosted tier must not imply exclusive ownership of free upstream public data. Any partner-licensed or restricted source should live behind source-specific terms and should be documented separately from the OSS licence.

## Migration Implications

If the project later moves from MIT to Apache-2.0:

- collect contributor consent or establish that all copyright ownership allows relicensing
- update `LICENSE`, package metadata, website copy, registry listings, and docs
- document the effective version and whether older releases remain MIT
- update DCO/CLA policy if inbound contribution terms change

If the project later adopts BSL-to-Apache for hosted-only code:

- split the repository or clearly separate source-available hosted code from OSS runtime code
- keep `sg_*` public-data contracts and country-pack contribution surfaces under an OSI-compatible licence where possible
- add explicit contributor notices before accepting patches to source-available code
- update buyer-facing and contributor-facing docs to avoid open-source mislabeling

## Recommendation

Use MIT through the current pivot. Revisit Apache-2.0 after named co-maintainers, public roadmap governance, and first enterprise procurement feedback. Avoid BSL-to-Apache unless a concrete hosted-only codebase exists and the project can explain the tradeoff without weakening OSS adoption.
