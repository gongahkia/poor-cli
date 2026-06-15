# Release Checklist

- Run `python -m pytest tests/ -q`.
- Run `ruff check src/poor_cli tests`.
- Run `mypy --strict src/poor_cli`.
- Run `mkdocs build --strict`.
- Run `python bench/replay_determinism_gate.py`.
- Run `python bench/loc_gate.py`.
- Run `python bench/packaging_gate.py`.
- Run `python bench/dogfood_report.py`.
- Run `python bench/release_gate.py`.
- Confirm live-provider tests are skipped unless `POOR_CLI_LIVE_PROVIDER_TESTS=1`.
- Review security docs and shell sandbox changes.
- Include benchmark report date, config, task set, pass rate, cost, and latency for any performance claim.
- Confirm backward compatibility for existing CLI commands and config files.
