# Phase 1 CLI and Config Spec

This document defines the first implementation target for Seuss. Phase 1 should stay small, CLI-first, and backend-oriented. The CLI exists to exercise the architecture; it should not become the architecture.

## Phase 1 Goal

Phase 1 should prove that Seuss can:

- Ingest configurable local corpora.
- Preserve provenance for every text fragment.
- Build simple memory and style artifacts.
- Generate text with a Jugemu-style continuation engine.
- Evaluate generated text against held-out source material.
- Keep live conversation memory separate from approved training data.

Phase 1 should not include LoRA, adapter training, web UI, remote sync, multi-user auth, or complex TUI behavior.

## CLI Shape

The first CLI can be minimal. A shell-style CLI is acceptable as long as commands are stable and backend logic is not embedded directly in command handlers.

Target commands:

```text
seuss init
seuss ingest
seuss inspect
seuss generate
seuss memory
seuss approve
seuss eval
seuss persona
```

### `seuss init`

Creates the project-local Seuss workspace.

Expected behavior:

- Create a default config if one does not exist.
- Create data directories.
- Create empty JSONL stores where needed.
- Refuse to overwrite existing config unless `--force` is passed.

Example:

```sh
seuss init
seuss init --config ./seuss.yaml
```

Expected files:

```text
seuss.yaml
.seuss/
  corpus/
  memory/
  evals/
  runs/
  training_queue.jsonl
  approved_training.jsonl
```

### `seuss ingest`

Loads configured sources into the corpus registry.

Expected behavior:

- Read enabled sources from config.
- Normalize text.
- Redact sensitive patterns where configured.
- Segment text into fragments.
- Attach provenance metadata.
- Deduplicate fragments.
- Write corpus records to `.seuss/corpus/fragments.jsonl`.

Example:

```sh
seuss ingest
seuss ingest --source notes
seuss ingest --path ../notes/user_style.md
seuss ingest --path ../docs_markdown
seuss ingest --dry-run
```

Useful flags:

- `--source <name>`: ingest only one configured source.
- `--path <relative-or-absolute-path>`: ingest a direct `.md`/`.txt` file or directory without adding it to config.
- `--dry-run`: show counts without writing.
- `--rebuild`: rebuild the fragment registry from scratch.
- `--config <path>`: use a non-default config.

### `seuss inspect`

Shows corpus, memory, and provenance summaries.

Expected behavior:

- Print fragment counts by source.
- Print fragment counts by provenance label.
- Print train/eval split counts.
- Print top repeated phrases.
- Print training queue summary and recent queue items.
- Print recent saved generation runs.
- Print redaction summary if available.

Example:

```sh
seuss inspect
seuss inspect corpus
seuss inspect source notes
seuss inspect phrases --limit 25
seuss inspect queue --limit 20
seuss inspect runs --limit 20
```

### `seuss generate`

Generates text using the Phase 1 Jugemu engine.

Expected behavior:

- Load corpus fragments and configured generation settings.
- Select a generation level: character, word, phrase, or hybrid.
- Generate a sample.
- Report generation metadata.
- Optionally write the output to a run log.

Example:

```sh
seuss generate --prompt "I think"
seuss generate --level phrase --max-tokens 120
seuss generate --level hybrid --seed 42
```

Useful flags:

- `--prompt <text>`: optional starting text.
- `--level <character|word|phrase|hybrid>`: continuation mode.
- `--max-tokens <n>`: generation length cap.
- `--temperature <n>`: sampling randomness.
- `--seed <n>`: reproducible generation.
- `--save`: write generation record to `.seuss/runs/`.

Phase 1 generation should be explicit about its limits. It is not expected to be a high-quality chatbot yet.

### `seuss memory`

Manages live and distilled memory.

Expected behavior:

- Show memory records.
- Add a manual memory.
- Import live conversation snippets as memory.
- Queue candidate training examples only when policy permits.
- Delete memory by ID.

Example:

```sh
seuss memory list
seuss memory add "Prefers direct, implementation-first answers."
seuss memory import ./chat.jsonl
seuss memory delete mem_123
```

Memory records should not automatically become training records unless config allows it.

### `seuss approve`

Reviews and approves queued training examples.

Expected behavior:

- Show pending examples from `.seuss/training_queue.jsonl`.
- Approve or reject examples.
- Move approved examples to `.seuss/approved_training.jsonl`.
- Preserve source provenance and approval metadata.

Example:

```sh
seuss approve list
seuss approve accept ex_123
seuss approve reject ex_124
seuss approve accept-all --source live_chat
```

This command exists because the default policy requires explicit approval before live conversation data becomes training data.

### `seuss eval`

Runs Phase 1 evaluations.

Expected behavior:

- Generate samples from held-out prompts.
- Compare generated text against held-out human-origin fragments.
- Report persona/style similarity.
- Report exact-copy rate.
- Report repetition/diversity.
- Report provenance and privacy checks.
- Write a reproducible eval report.

Example:

```sh
seuss eval
seuss eval --suite phase1
seuss eval --seed 42
seuss eval --output .seuss/evals/phase1.json
seuss eval --summary
seuss eval --summary --fail-on-thresholds
```

### `seuss persona`

Builds and inspects a distilled persona profile from train fragments and memory hints.

Expected behavior:

- Produce a baseline persona profile (`voice`, `lexical`, `memory_hints`).
- Save profile to `.seuss/memory/persona_profile.json` by default.
- Show a concise summary for terminal inspection.

Example:

```sh
seuss persona build
seuss persona build --output .seuss/memory/persona_profile_v2.json
seuss persona show
seuss persona show --input .seuss/memory/persona_profile_v2.json
```

## Default Config

Phase 1 should use a project-local YAML config.

Default path:

```text
./seuss.yaml
```

Proposed initial config:

```yaml
project:
  name: seuss
  workspace: ./.seuss

sources:
  - name: notes
    type: directory
    path: ./data/notes
    enabled: true
    include:
      - "*.txt"
      - "*.md"
    provenance: human_original

  - name: chat_export
    type: jsonl
    path: ./data/chat_export.jsonl
    enabled: false
    text_field: text
    speaker_field: speaker
    timestamp_field: timestamp
    provenance: human_original

privacy:
  redact:
    emails: true
    phone_numbers: true
    urls: false
    custom_patterns: []

segmentation:
  paragraph: true
  sentence: true
  phrase: true
  word: true
  character: true
  min_fragment_chars: 3
  max_fragment_chars: 2000

splits:
  strategy: time
  train_ratio: 0.8
  eval_ratio: 0.2
  seed: 42

adaptation:
  live_memory:
    enabled: true
    summarize_after_each_turn: true

  live_training_data:
    enabled: false
    require_explicit_approval: true
    queue_path: ./.seuss/training_queue.jsonl

  auto_training_data:
    enabled: false
    min_quality_score: 0.8
    allow_ai_generated: false

generation:
  default_level: hybrid
  max_tokens: 120
  temperature: 0.8
  seed: 42

  jugemu:
    character_order: 5
    word_order: 3
    phrase_order: 2
    sentence_order: 1
    motif_order: 2
    anti_copy_ngram: 12
    backoff: true

evaluation:
  exact_copy_ngram: 12
  heldout_required: true
  report_path: ./.seuss/evals
  thresholds:
    persona_match_min: 0.15
    exact_copy_rate_max: 0.05
    repetition_score_max: 0.6
    privacy_leak_count_max: 0
```

## Data Records

All persistent records should be JSONL in Phase 1. This keeps the system easy to inspect and avoids premature database design.

### Corpus Fragment Record

Stored in:

```text
.seuss/corpus/fragments.jsonl
```

Shape:

```json
{
  "id": "frag_001",
  "source": "notes",
  "source_path": "./data/notes/example.md",
  "provenance": "human_original",
  "text": "Example fragment text.",
  "normalized_text": "Example fragment text.",
  "segment_type": "sentence",
  "created_at": "2026-04-20T00:00:00Z",
  "metadata": {
    "line_start": 1,
    "line_end": 1
  }
}
```

### Memory Record

Stored in:

```text
.seuss/memory/memories.jsonl
```

Shape:

```json
{
  "id": "mem_001",
  "kind": "style",
  "text": "Prefers concise, direct engineering answers.",
  "source": "manual",
  "provenance": "memory_summary",
  "created_at": "2026-04-20T00:00:00Z",
  "confidence": 0.8,
  "approved_for_training": false
}
```

### Training Queue Record

Stored in:

```text
.seuss/training_queue.jsonl
```

Shape:

```json
{
  "id": "ex_001",
  "text": "Candidate training example.",
  "source": "live_chat",
  "provenance": "conversation_live",
  "created_at": "2026-04-20T00:00:00Z",
  "approval_status": "pending",
  "quality_score": null,
  "notes": []
}
```

### Generation Run Record

Stored in:

```text
.seuss/runs/*.json
```

Shape:

```json
{
  "id": "run_001",
  "prompt": "I think",
  "output": "I think this needs a cleaner boundary first.",
  "level": "hybrid",
  "config_hash": "sha256:...",
  "seed": 42,
  "created_at": "2026-04-20T00:00:00Z",
  "metrics": {
    "exact_copy_ngram_hits": 0,
    "repetition_score": 0.12
  }
}
```

## Backend Boundaries

The CLI should call backend modules with narrow responsibilities.

Recommended first boundaries:

- `config`: load, validate, and normalize config.
- `sources`: discover and read configured inputs.
- `corpus`: normalize, redact, segment, deduplicate, and store fragments.
- `provenance`: validate labels and metadata.
- `memory`: create, list, delete, and import memory records.
- `approval`: queue, approve, and reject training examples.
- `jugemu`: build continuation indexes and generate text.
- `evals`: run metrics and write reports.
- `cli`: parse args and call backend services.

The CLI should not parse corpora, implement generation, or compute eval metrics directly.

## Phase 1 Non-Goals

Do not implement these in Phase 1:

- LoRA or neural adapter training.
- Full model fine-tuning.
- Web UI.
- Cloud sync.
- Multi-user accounts.
- Vector database dependency.
- Heavy TUI framework.
- Autonomous self-play agents.
- LLM-as-judge evaluation.

These belong to later phases after corpus, provenance, memory, generation, and baseline evaluation are stable.

## Implementation Biases

Prefer simple, inspectable choices:

- Plain files over databases.
- JSONL over binary formats.
- Deterministic seeds for generation and eval.
- Local-first storage.
- Explicit config over hidden defaults.
- Small backend modules over a large CLI script.

The project can still expose shell-like commands, but the internals should be structured enough to support the later research roadmap.
