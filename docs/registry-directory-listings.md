# Registry And Directory Listing Tracker

This tracker keeps Swee SG's external discovery metadata explicit. It is a readiness and submission log, not proof that a third-party directory has accepted or indexed the project.

Observed on 2026-05-17.

## Success Definition

- Smithery, Glama, and official MCP registry metadata are current for the shipped surface.
- Every target registry or directory has a submission path, status, and accepted URL field.
- External acceptance, manual review, namespace verification, or packaging gaps are tracked as follow-up issues instead of silently blocking repo-side closure.

## Metadata Verification

| Surface | Local file | Required state | Current status |
| --- | --- | --- | --- |
| Official MCP Registry | [server.json](../server.json) | Uses the 2025-12-11 schema, `io.github.gongahkia/swee-sg`, GHCR package metadata, and Pulse/Shield wording. The npm package entry stays omitted until `@swee-sg/shield` is public. | Ready for submission after publisher namespace and package ownership checks. |
| Smithery | [smithery.yaml](../smithery.yaml) | Uses `swee-sg`, stdio transport, and the local npm/build/start install command. | Ready for local listing or bundle review; hosted URL listing needs a public `/mcp` endpoint. |
| Glama | [glama.json](../glama.json) | Uses `swee-sg`, stdio transport, the same install command, and canonical GitHub repository. | Ready for indexing or claim flow. |
| README | [README.md](../README.md) | Surface snapshot lists Swee Pulse, Swee Shield, retained source adapters, and ops tools. | Current. |

Run this check before external submission:

```bash
npm run registry:metadata:check
```

## Target Directory Queue

| Target | Submission path | Status | Accepted URL |
| --- | --- | --- | --- |
| Official MCP Registry | Publish `server.json` through the official registry flow after namespace/package ownership verification. | External submission pending. | TBD |
| Smithery | Submit through Smithery's publish flow or package/bundle flow depending on whether the target is local stdio or hosted Streamable HTTP. | External submission pending. | TBD |
| Glama | Submit or claim the server listing and verify the scanned install metadata. | External submission pending. | TBD |
| MCP-Hive | Manual directory submission or maintainer request. | External submission pending. | TBD |
| Awesome-MCP | Pull request adding Swee SG with a short source-backed description. | External submission pending. | TBD |
| mcp.so | Directory submission or listing claim after package metadata is public. | External submission pending. | TBD |

## External Blockers To Track Separately

- Official registry acceptance depends on publisher authentication and package ownership checks outside this repository.
- Smithery hosted publication depends on either a public Streamable HTTP `/mcp` endpoint or a packaged local artifact accepted by Smithery.
- Third-party directories may require manual maintainer review, screenshots, category choices, or listing edits.
- Accepted URLs must be written back here only after the listing is live.

## Listing Copy

Short description:

> Swee SG is a policy-governed Singapore public-data runtime with Pulse city signals, Shield audit trails, and retained raw source adapters.

Category candidates:

- Singapore
- city operations
- public data
- source health
- MCP security

Important caveat:

Swee SG surfaces public-data signals, provenance, freshness, gaps, and limits. It does not provide legal, tax, AML, sanctions, credit, investment, safety, medical, or licensed compliance advice.
