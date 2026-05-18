# Pivot Issue Status

This page records how roadmap parent issues are resolved when child work is either complete in the repository or intentionally moved into narrower external follow-up issues.

Updated on 2026-05-18.

## Rule

Close the original implementation issue when repo-side work is complete. If the remaining work requires a third-party approval, account permission, registry acceptance, outreach response, named participant, or other external action, open a new issue with `External blocker` in the title and link it from the closure note.

## Corp-Services CDD Pivot

Parent issue: `#97`.

| Child | Repo-side status | External follow-up |
| --- | --- | --- |
| `#40` Macro brief CPI dataset resolution | Closed. | None. |
| `#41` Primary corp-services CDD onboarding flow | Closed. | None. |
| `#42` Vendor onboarding and procurement secondary workflows | Closed. | None. |
| `#56` PDPA s.24/s.26 vendor-diligence checklist and report | Closed. | None. |

Roadmap status: child work is complete, the README points builders to the primary corp-services CDD workflow, and the roadmap index links both the primary CDD lane and secondary workflow lane, so `#97` can close.

## Workspace Platform And Dude Cloud Foundations

Parent issue: `#98`.

| Child | Repo-side status | External follow-up |
| --- | --- | --- |
| `#43` Workspace accounts, multi-seat isolation, and RBAC | Closed. | None. |
| `#44` Google/Microsoft SSO and 2FA posture | Closed. | None. |
| `#45` Persist dossiers to workspace folders | Closed. | None. |
| `#46` Signed export manifests for PDF, CSV, and JSON dossiers | Closed. | None. |
| `#47` Audit log with actor, dataset version, and content hash | Closed. | None. |
| `#48` Workspace-backed watchlists and alert rules | Closed. | None. |
| `#49` Workspace-backed 200-row bulk CSV diligence | Closed. | None. |
| `#50` Dude Cloud hosted-tier entitlements and billing boundaries | Closed. | None. |
| `#51` Dude Cloud deployment and security architecture | Closed. | None. |

Roadmap status: the platform-foundation child issues are complete and the product, hosted-security, SOC 2, MAS, export-manifest, and workspace docs now distinguish implemented repo primitives from remaining hosted operating evidence, so `#98` can close.

## Diligence Depth Integrations And SG Risk Rules

Parent issue: `#99`.

| Child | Repo-side status | External follow-up |
| --- | --- | --- |
| `#52` OpenSanctions screening tool | Closed. | None. |
| `#53` OpenCorporates entity cross-links | Closed. | None. |
| `#54` Adverse-media lite from bounded public feeds | Closed. | None. |
| `#55` Shallow UBO and corporate relationship graph | Closed. | None. |
| `#57` Open YAML SG risk rules pack | Closed. | None. |
| `#58` Benchmark set for 50 diligence edge cases | Closed. | None. |

Roadmap status: the external-diligence adapters, official-feed adverse-media lane, shallow relationship graph, risk rules pack, and diligence benchmark set are documented and referenced from the product workflow docs, so `#99` can close.

## Country-Pack Architecture And ASEAN Expansion

Parent issue: `#101`.

| Child | Repo-side status | External follow-up |
| --- | --- | --- |
| `#73` Refactor server into country-pack architecture | Closed. | None. |
| `#74` Define country-pack envelope contract and contribution guide | Closed. | None. |
| `#75` Malaysia country-pack skeleton | Closed. | None. |
| `#76` Philippines country-pack skeleton | Closed. | None. |
| `#77` Indonesia country-pack skeleton | Closed. | None. |
| `#78` Thailand public-only country-pack skeleton | Closed. | None. |
| `#79` Vietnam feasibility and community-contribution path | Closed. | None. |
| `#95` ASEAN paid-data licensing assumptions | Closed. | None. |

Roadmap status: the country-pack runtime boundary, contribution envelope, ASEAN skeleton fixtures, Vietnam feasibility note, and paid-data licensing assumptions are complete and linked from the roadmap and contribution docs, so `#101` can close.

## OSS Distribution And Governance

Parent issue: `#100`.

| Child | Repo-side status | External follow-up |
| --- | --- | --- |
| `#62` Publish `@dude/mcp` to npm | Complete. | None. |
| `#63` Publish `@dude/sdk` to npm | Complete or moved before this pass. | See issue history. |
| `#64` List Dude on MCP registries and directories | Metadata tracker and validation are complete. | Registry acceptance/submission follow-up required. |
| `#65` Contributing, code of conduct, governance | Complete or moved before this pass. | See issue history. |
| `#66` CLA/DCO | Complete or moved before this pass. | See issue history. |
| `#67` Neutral-home donation proposal | Complete or moved before this pass. | See issue history. |
| `#68` License strategy | Complete or moved before this pass. | See issue history. |
| `#69` Public GitHub Projects roadmap | Board spec is complete. | GitHub Projects permission follow-up required. |
| `#70` Reference deployments | Reference program and permission path are complete. | Named references require external permission. |
| `#71` Versioned schemas/changelog | Complete or moved before this pass. | See issue history. |
| `#72` Benchmark/uptime page | Complete or moved before this pass. | See issue history. |
| `#94` Co-maintainer recruitment | Governance and recruitment plan are complete. | Named maintainer acceptance requires external recruitment. |

Roadmap status: repo-side work is complete and remaining unfulfilled actions are external follow-ups, so `#100` can close after the linked follow-up issues exist.

## Compliance And Go-To-Market Readiness

Parent issue: `#102`.

| Child | Repo-side status | External follow-up |
| --- | --- | --- |
| `#80` ACRA licensing track | Complete or moved before this pass. | See issue history. |
| `#81` OneMap/URA commercial-use review | Complete or moved before this pass. | See issue history. |
| `#82` PDPA/DPO readiness | Complete or moved before this pass. | See issue history. |
| `#83` DPA template | Complete or moved before this pass. | See issue history. |
| `#84` MAS outsourcing readiness | Complete or moved before this pass. | See issue history. |
| `#85` SOC 2 Type I roadmap | Complete or moved before this pass. | See issue history. |
| `#86` Compliance-use clauses | Complete or moved before this pass. | See issue history. |
| `#87` PSG application track | Complete. | None. |
| `#88` Accreditation track | Complete or moved before this pass. | See issue history. |
| `#89` Professional-body outreach | Complete or moved before this pass. | See issue history. |
| `#90` Case-study content engine | Complete. | None. |
| `#91` Corp-services affiliate outreach | Pitch, target hypotheses, terms, and tracker are complete. | External outreach follow-up required. |
| `#92` Big-4 innovation lab pilot | Pilot packet and MOU scope are complete. | External intro/outreach follow-up required. |
| `#93` Consulting partner program | Complete or moved before this pass. | See issue history. |
| `#96` Private beta with two corp-secretarial firms | Beta plan and feedback workflow are complete. | External participant recruitment/execution follow-up required. |

Roadmap status: repo-side readiness work is complete and remaining unfulfilled actions require external parties, so `#102` can close after the linked follow-up issues exist.
