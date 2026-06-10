# Private Beta Plan For Corp-Secretarial Firms

This plan defines how to run a private beta with two Singapore corp-secretarial firms once external participants are recruited. It is a beta readiness packet, not evidence that a beta has run.

## Success Definition

- Two-firm beta criteria and recruitment profile are clear.
- Data-handling constraints are explicit.
- Onboarding workflow and approved test-case structure are ready.
- Feedback conversion into prioritized issues is defined.
- Actual recruitment and beta execution are tracked externally.

## Firm Profile

Each beta firm should have:

- recurring Singapore entity onboarding or periodic-review workflows;
- a named operational owner and one or more analysts who do manual checks today;
- willingness to use public-only, synthetic, or customer-approved test cases first;
- ability to review provenance, freshness, gaps, limits, and export artifacts;
- no requirement that Dude provide legal, tax, AML, sanctions, credit, investment, audit, or licensed compliance advice.

## Success Criteria

| Criterion | Target |
| --- | --- |
| Onboarding clarity | Firm can complete a company/UEN search and read source/gap state without maintainer intervention. |
| Evidence usefulness | Dossier/export artifacts map to at least one real onboarding or review checklist. |
| Time signal | Analysts can identify where Dude saves manual checking time or where it does not. |
| Gap clarity | Skipped sector modules and no-match states are interpreted correctly. |
| Safety | No unsupported compliance/pass-fail claims are made. |
| Feedback quality | At least five actionable product/issues are generated across the two firms. |

## Data Handling Constraints

- Start with synthetic, public demo, or customer-approved entities.
- Do not process confidential client records until hosted beta controls, DPA review, retention/deletion path, audit logs, and support owner are ready.
- Do not publish firm names, logos, quotes, screenshots, UENs, or metrics without written permission.
- Preserve source provenance, freshness, gaps, limits, and non-advice copy in all shared artifacts.
- Treat any customer-provided notes as confidential unless explicitly approved for issue reproduction.

## Onboarding Workflow

1. Confirm firm owner, analysts, workflow, data boundary, and success criteria.
2. Run a 30-minute setup call using the local or hosted beta environment.
3. Execute three approved scenarios:
   - exact UEN/company identity lookup;
   - sector-module rerun with supplied sector context or identifiers;
   - export and analyst handoff review.
4. Capture screenshots or exported artifacts approved for internal review.
5. Run a feedback session with the beta owner and analysts.
6. Convert feedback into GitHub issues with labels, priority, evidence, and reproduction steps.
7. Close beta with a go/no-go note and permission decision for named/anonymized reference use.

## Feedback Issue Template

```markdown
## Source

Private beta feedback from [firm or anonymized segment], observed on [date].

## Workflow

- Scenario:
- Input type:
- Data approval boundary:
- Screenshot/export evidence:

## Problem

## Expected behavior

## Definition of done

- [ ] 

## Caveats

- Public-data limits:
- Non-advice boundary:
- Confidentiality:
```

## Recruitment Tracker

| Firm | Status | Data boundary | Owner | Next step | External blocker |
| --- | --- | --- | --- | --- | --- |
| Firm A | Not recruited. | TBD | TBD | Identify and contact candidate. | Requires external recruitment. |
| Firm B | Not recruited. | TBD | TBD | Identify and contact candidate. | Requires external recruitment. |

## Exit Decision

The beta can be considered complete only after two firms complete onboarding and feedback is converted into prioritized issues. Until then, this document is the operating plan and the active blocker is external participant recruitment.
