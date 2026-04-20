# Wok Release Hardening

This document tracks release-quality controls for Wok artifacts.

## Current Automated Gates

Release workflow (`.github/workflows/release.yml`) now enforces:

- Per-artifact SHA256 generation.
- Checksum coverage validation (every packaged artifact has a checksum line).
- `sha256sum -c` verification before publishing.
- Archive smoke checks:
  - `.tar.gz` contains `wok` binary.
  - `-app.tar.gz` contains `Wok.app`.
  - `.zip` contains `wok.exe`.
  - `.deb` parses with `dpkg-deb --info`.
- SBOM generation (`syft`, CycloneDX JSON) and publication as a release artifact.
- Keyless Sigstore signing for `checksums.sha256`, with in-workflow signature verification.
- GitHub build provenance attestation for published release artifacts.

## Remaining Hardening Backlog

1. Reproducible build attestations
2. Staged rollout with rollback playbook
3. CVE scanning on release artifacts

## Operator Checklist (Manual)

1. Confirm tag points to the intended commit.
2. Verify CI + release workflow pass on all targets.
3. Validate checksums against downloaded artifacts.
4. Verify Sigstore signature and certificate identity for `checksums.sha256`.
5. Verify GitHub attestation for shipped artifacts.
6. Spot-test install + launch on macOS, Linux, and Windows.
7. Publish release notes with upgrade and rollback instructions.
