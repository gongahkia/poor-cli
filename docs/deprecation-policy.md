# Deprecation Policy

## Intent

Deprecations are allowed only when migration is explicit and time-bounded.
Silent surface breakage is not acceptable.

## Policy

1. Every deprecation must state scope, reason, and target removal window.
2. Every deprecation must provide at least one migration path.
3. Every deprecation must include release-note entries until removal completes.
4. Removed surfaces must reference the final supported replacement in docs.

## Deprecation Notice Template

Use this template in release notes and migration docs.

```md
### Deprecation Notice: <surface name>

- Announced in: <version>
- Planned removal: <version or date>
- Scope: <tool/resource/workflow/field>
- Reason: <stability, licensing, upstream break, consolidation>
- Migration path: <replacement entrypoint and payload mapping>
- Verification command: <smoke/test command>
```

## Migration Mapping Template

```md
| Deprecated surface | Replacement | Input mapping | Output mapping | Notes |
| --- | --- | --- | --- | --- |
| <old> | <new> | <arg transforms> | <field transforms> | <compat caveats> |
```
