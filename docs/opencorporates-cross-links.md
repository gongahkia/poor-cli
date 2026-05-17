# OpenCorporates Cross-Link Policy

`sg_opencorporates_links` is an identifier cross-link tool. It returns candidate OpenCorporates company records for the supplied Singapore entity name or UEN and keeps ambiguous candidates visible instead of collapsing them into a single asserted match.

Success criteria:

- require `OPENCORPORATES_API_TOKEN`
- default `jurisdictionCode` to `sg`
- preserve provenance and freshness
- return no-match and upstream-failure gaps
- avoid ownership, control, parent/subsidiary, or UBO claims

Use this as a follow-up from a dossier or in `includeExternalDiligence` mode when licensed usage is configured.
