# Wok Release Hardening

This document tracks release-quality controls for Wok artifacts.

## Current Automated Gates

Release workflow (`.github/workflows/release.yml`) now enforces:

- Per-artifact SHA256 generation.
- Checksum coverage validation (every `wok-*` artifact has a checksum line).
- `sha256sum -c` verification before publishing.
- Archive smoke checks:
  - `.tar.gz` contains `wok` binary.
  - `-app.tar.gz` contains `Wok.app`.
  - `.zip` contains `wok.exe`.
  - `.deb` parses with `dpkg-deb --info`.

## Remaining Hardening Backlog

1. Signing and provenance
2. SBOM generation and publication
3. Reproducible build attestations
4. Staged rollout with rollback playbook
5. CVE scanning on release artifacts

## Operator Checklist (Manual)

1. Confirm tag points to the intended commit.
2. Verify CI + release workflow pass on all targets.
3. Validate checksums against downloaded artifacts.
4. Spot-test install + launch on macOS, Linux, and Windows.
5. Publish release notes with upgrade and rollback instructions.
