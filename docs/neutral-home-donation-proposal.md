# Neutral-Home Donation Proposal

This proposal evaluates whether Dude MCP should move to a neutral home such as a foundation, fiscal host, public-good lab, or open-source governance body. It is a decision memo, not a submitted application.

## Success Definition

- Candidate neutral homes are identified with submission/contact paths.
- Governance, trademark, package, maintainer, and commercial implications are explicit.
- The recommended decision and next step are recorded.
- Follow-up tasks are scoped before any external approach.

## Source Baseline

Observed on 2026-05-17:

- [Open Source Collective](https://docs.oscollective.org/) describes itself as a nonprofit fiscal host for open source projects. Its [project page](https://oscollective.org/projects/) says fiscal hosting gives projects legal status and use of OSC's bank account, with third-party agreements requiring written sign-off by OSC admins.
- [LF AI & Data](https://lfaidata.foundation/home/) says it supports and sustains open source AI and data projects in a neutral environment with open governance and invites open-source AI or data projects to contact the foundation about hosting.
- The [OpenJS Foundation project page](https://openjsf.org/about/project-funding-opportunities/) describes hosted JavaScript projects and states that the Cross Project Council oversees incubation for projects seeking OpenJS hosting.
- [LF Projects trademark policy](https://lfprojects.org/policies/trademark-policy/) documents trademark ownership and permitted-use expectations for LF-hosted project marks.
- [Open Government Products open-source page](https://www.open.gov.sg/resources/opensource) lists OGP open-source products and contact links, but it is a Singapore government product team rather than a general public fiscal host for external projects.

## Project Posture

Dude MCP is currently best described as:

- a Singapore public-data MCP runtime with stable `sg_*` tool contracts;
- a web-first CDD product surface built on the runtime;
- an early open-source project with hosted-commercial ambitions, source-licensing gates, and several unresolved cloud controls;
- a public-good-adjacent data interoperability project, not yet a broadly governed community project.

Moving to a neutral home would make sense only if it improves trust, contribution flow, source stewardship, funding, or institutional adoption more than it slows down product iteration.

## Candidate Homes

| Candidate | Fit | Submission / contact path | Main risk |
| --- | --- | --- | --- |
| Open Source Collective | Strong fit for donation/fiscal hosting without transferring technical governance. | Apply as an open-source project through OSC/Open Collective fiscal-hosting flow. | Fiscal hosting is not neutral technical governance; agreements need OSC admin sign-off. |
| LF AI & Data | Plausible fit if Dude becomes a broader open data / agent data infrastructure project with multiple maintainers and adopters. | Contact LF AI & Data about hosting an open-source AI/data project; prepare project proposal, governance, adopters, and IP posture. | Premature foundation approach without community/adopter evidence may fail or create overhead. |
| OpenJS Foundation | Limited fit because Dude is TypeScript/Node-based, but its core value is Singapore public data and MCP, not a broadly reusable JavaScript platform. | Cross Project Council incubation path for OpenJS-hosted projects. | Domain mismatch; hosted project obligations may not match data-governance needs. |
| Open Government Products | Good philosophical/public-good adjacency in Singapore, but not a normal external project donation home. | Contact OGP only after a concrete public-sector use case or collaboration lead exists. | Government ownership/endorsement confusion; likely inappropriate for an external commercial/open-source hybrid. |
| Independent Singapore nonprofit / university lab | Potential long-term fit if public-interest governance becomes the priority. | Identify sponsor, legal entity, board, and grant/funding path. | High setup burden and unclear maintainer incentives. |

## Donation Models

| Model | What transfers | What stays with current maintainers | When to choose |
| --- | --- | --- | --- |
| Fiscal hosting only | Donation collection, reimbursement, transparent budget. | Repository, npm packages, trademarks, roadmap, releases, technical governance. | Best first step if community funding starts before governance transfer. |
| Foundation sandbox/incubation | Repository governance, project charter, neutral technical oversight, possibly trademarks. | Maintainer roles continue under foundation rules. | Choose when there are multiple institutional adopters and maintainers. |
| Full trademark/IP donation | Project name, logos, marks, repository ownership, possibly package control. | Maintainers become project participants under donated governance. | Choose only after legal review and community consensus. |
| Public-sector collaboration | Specific deployment, data workflow, or public-good extension. | OSS repo and product ownership unless separately transferred. | Choose when a real agency/lab wants to sponsor a narrowly scoped public benefit. |

## Governance Implications

Before any foundation approach, Dude needs:

- a public maintainer list with role expectations;
- a documented technical steering process;
- a conflict-of-interest policy for hosted-commercial decisions;
- a security reporting and embargo process that foundation staff can operate;
- a contributor licence or DCO position that survives repository transfer;
- release authority rules for the `sg_*` public contract surface;
- a source-licensing policy for ACRA, OneMap, URA, LTA, and future country packs.

The existing maintainer governance document is a starting point, but it is not yet a foundation-grade project charter.

## Trademark And Package Implications

Potentially affected assets:

- product/project marks: `Dude`, `Dude MCP`, logo, domain names;
- npm packages: `@swee-sg/shield`, `@swee-sg/shared`, `@swee-sg/sdk`, executable aliases;
- GitHub repository ownership and issue/PR history;
- MCP server name and registry/listing metadata;
- documentation URLs and hosted product marks.

Risks:

- foundation or fiscal-host trademark policy may restrict how the commercial hosted product can use `Dude`;
- package ownership transfer can affect npm automation, provenance, 2FA, and release recovery;
- commercial cloud branding may need a separate mark from the neutral OSS project;
- downstream users need a migration notice if repository, package, or governance URLs change.

Recommended guardrail: do not donate trademarks or npm package ownership until there is a signed governance/brand plan that preserves OSS continuity and clearly separates any paid hosted product.

## Maintainer Implications

Neutral hosting changes maintainer work:

- more formal proposal writing, meetings, voting, and public roadmapping;
- clearer release and security obligations;
- more scrutiny on commercial roadmap choices;
- slower but more credible source-licensing and public-data stewardship decisions;
- better institutional adoption if multiple firms or public-interest groups participate.

Current project state suggests maintainer time is better spent first on hosted controls, source licensing, reference deployments, and external adopter evidence.

## Recommendation

Do not pursue full project donation yet.

Recommended path:

1. Keep the repository under current ownership while the hosted architecture, entitlements, audit log, persistence, SSO/RBAC, and source-licensing gates are still being shaped.
2. Prepare Open Source Collective fiscal hosting only if donations or sponsored work need transparent handling before a legal entity exists.
3. Revisit LF AI & Data after there are at least three independent production or pilot adopters, two non-founder maintainers, and a stable project charter.
4. Treat OpenJS as a low-priority option unless Dude's reusable JavaScript SDK/widget ecosystem becomes the main adoption vector.
5. Treat OGP/public-sector outreach as collaboration, not donation, unless OGP explicitly invites the project into a public-sector product path.

## External Approach Packet

Prepare before contacting any neutral home:

- one-page project brief and problem statement;
- current adoption evidence and reference deployments;
- maintainer list and governance draft;
- licence, DCO/CLA, trademark, and package ownership inventory;
- source-licensing risk register;
- security policy and vulnerability handling process;
- public roadmap and issue labels;
- funding needs and budget, if asking for fiscal hosting.

## Follow-Up Issues

- Draft a foundation-ready project charter after the hosted controls backlog stabilizes.
- Create a trademark/package ownership inventory for `Dude`, `@dude/*`, domains, and registry metadata.
- Add a fiscal-hosting readiness checklist if external donations become likely.
- Collect adopter evidence from beta/reference deployments before any LF AI & Data inquiry.

## Decision

Current decision: defer full donation, keep ownership stable, and prepare only the artifacts that make a later neutral-home move low-risk.

Next concrete step: create the trademark/package inventory before any external outreach.
