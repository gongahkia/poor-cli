# DCO Sign-Off Policy

Dude uses the Developer Certificate of Origin (DCO) instead of a Contributor Licence Agreement (CLA).

## Decision

Use DCO sign-off for all external contributions.

## Why DCO

- It is lightweight for an open-source public-data runtime.
- It keeps contribution friction low for country-pack and documentation contributors.
- It creates an explicit contributor attestation in git history without requiring a separate identity, contract, or hosted CLA service.
- It fits the current MIT licence and avoids delaying community work while the project is still pre-foundation and pre-neutral-home.

## Why Not CLA Now

- A CLA adds legal and administrative overhead before there is a foundation, company-controlled contributor programme, or dual-licensing plan.
- A CLA does not solve upstream public-data licensing constraints; those still need source-specific review.
- If the project later changes licence strategy or moves to a foundation, the maintainer team can revisit this decision with the criteria in [license-strategy.md](./license-strategy.md).

## How Contributors Comply

Every commit from an external contributor must include a sign-off trailer:

```text
Signed-off-by: Your Name <you@example.com>
```

Use git's built-in sign-off flag:

```bash
git commit -s -m "Describe the change"
```

For an existing commit:

```bash
git commit --amend -s --no-edit
```

For multiple commits, rebase and amend each commit that needs the trailer.

## Local Check

Run the local DCO checker against the commits in your branch:

```bash
npm run dco:check -- --range origin/main..HEAD
```

The checker validates that each commit in the selected range has at least one `Signed-off-by:` trailer in the conventional `Name <email>` format.

## Maintainer Override Policy

Maintainers may merge an unsigned commit only when all of the following are true:

- the author is a maintainer or the contributor has confirmed the sign-off in the pull request
- rewriting history would create disproportionate operational risk
- the pull request records the override reason
- the merge commit or follow-up commit includes a maintainer sign-off

Overrides are not allowed for new country packs, data-licensing changes, security-sensitive changes, or contributions with unclear authorship.
