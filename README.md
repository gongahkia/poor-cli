# Seuss

Seuss is a research-first persona-adaptive text generation project.

Current implementation target is Phase 1 from `docs/PHASE1_CLI_CONFIG_SPEC.md`:

- Configurable corpus ingestion
- Provenance-aware fragment storage
- Memory and training approval queue separation
- Jugemu-style Markov generation (character/word/phrase/hybrid)
- Baseline evaluation reports

## Quick start

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
seuss init
seuss ingest
seuss ingest --path ../some/relative/path/to/file.md
seuss ingest --path ../some/relative/path/to/docs_dir
seuss inspect
seuss generate --prompt "I think"
seuss eval --summary
seuss eval --summary --fail-on-thresholds
seuss persona build
seuss persona show
make compile
make test
make smoke
```

## Notes

- Phase 1 is intentionally CLI-first and architecture-first.
- LoRA and neural weight adaptation are scheduled for later phases.
