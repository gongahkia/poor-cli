# Seuss Research Roadmap

Seuss is a research-first persona-adaptive text generation framework. The first versions should optimize for clean architecture, reproducible experiments, and defensible research claims rather than chatbot polish.

The long-term direction is a useful CLI/TUI chatbot, but the early phases should prove whether the underlying adaptation, memory, generation, and evaluation loops work.

## Product Stance

- Primary near-term goal: research platform.
- Long-term goal: useful personalized CLI/TUI chatbot.
- Interface scope: CLI/TUI only for now.
- Core behavior: adapt to a person, not impersonate a person.
- Default live-data policy: conversations may become memory immediately, but they do not become training data without explicit approval.
- Configurable override: users may opt into automatic training-data inclusion from live conversations through a config file.
- Neural weight updates: out of scope for the first phase; LoRA/adapters and model-weight training are future phases.

## Research Thesis

Seuss should combine classical sequence modeling with modern LLM personalization instead of treating either approach as sufficient.

The central research idea is a Jugemu-style hierarchical continuation engine. Rather than only predicting the next token, Seuss should model continuations at several levels:

- Character habits: casing, punctuation, repeated symbols, spelling quirks.
- Word transitions: local lexical style and repeated vocabulary.
- Phrase recurrence: catchphrases, idioms, openings, closings, transitions.
- Sentence shape: length, clause structure, bullet usage, question frequency.
- Discourse motifs: recurring argument structures and conversational moves.
- Persona memory: stable facts, preferences, boundaries, and interaction style.

This lets Seuss preserve stylistic fingerprints without relying entirely on neural fine-tuning.

## Data Policy

Every text fragment should carry provenance metadata. This is required for privacy, evaluation, model-collapse prevention, and reproducibility.

Required provenance labels:

- `human_original`
- `human_edited`
- `conversation_live`
- `memory_summary`
- `ai_generated`
- `ai_edited`
- `synthetic_adversarial`
- `synthetic_selfplay`

The system should avoid blindly retraining on its own outputs. Synthetic data may be useful, but only when labeled, filtered, evaluated, and mixed with enough human-origin data.

## Configuration Direction

Live adaptation should be controlled by config. The default should be conservative.

```yaml
adaptation:
  live_memory:
    enabled: true
    summarize_after_each_turn: true

  live_training_data:
    enabled: false
    require_explicit_approval: true
    queue_path: ./data/training_queue.jsonl

  auto_training_data:
    enabled: false
    min_quality_score: 0.8
    allow_ai_generated: false
```

If a user deliberately opts into automatic training-data inclusion, the config can permit it:

```yaml
adaptation:
  live_training_data:
    enabled: true
    require_explicit_approval: false
    queue_path: ./data/approved_live_training.jsonl
```

The implementation should make this explicit in logs so users can audit when conversation data becomes training material.

## Backend Architecture Priorities

The first architectural priority is a clean pipeline, not a polished terminal UI.

Target pipeline:

```text
sources
  -> ingestion
  -> normalization
  -> redaction
  -> segmentation
  -> provenance labeling
  -> persona distillation
  -> memory indexing
  -> Jugemu generation
  -> evaluation
```

Core modules should stay loosely coupled:

- `sources`: configurable corpus loaders.
- `corpus`: normalization, segmentation, deduplication, redaction.
- `memory`: structured memory and vector retrieval.
- `persona`: voice/profile distillation.
- `jugemu`: character, word, phrase, sentence, and motif-level continuation.
- `generation`: model backend interface and response composition.
- `evals`: authorship, persona-match, privacy, repetition, and stability checks.
- `arena`: adversarial/self-play experiments.
- `cli`: thin command interface over the backend.
- `tui`: optional future terminal UI layer.

The CLI should be thin. Most behavior should live in backend services so the project can later support a TUI, API, or notebook interface without rewriting core logic.

## Phase Definitions

### Phase 0: Research Scaffold

Goal: define the research surface before implementation.

Success means:

- The repo has a clear research roadmap.
- The default data and adaptation policies are explicit.
- Future neural-weight training is documented but not prematurely implemented.
- The first implementation target is constrained to CLI/TUI plus backend architecture.

Implementation detail: Phase 1 command and config behavior is specified in `docs/PHASE1_CLI_CONFIG_SPEC.md`.

### Phase 1: Corpus, Memory, and Jugemu MVP

Goal: prove that configurable corpus ingestion and hierarchical continuation can produce measurable persona/style signals.

Expected features:

- Config-driven local source ingestion for text, Markdown, and JSONL.
- Message/paragraph/sentence/phrase/word/character segmentation.
- Provenance metadata for every fragment.
- Conservative live memory capture.
- Explicit training-data approval queue.
- Character-level, word-level, and phrase-level Jugemu generator.
- Basic CLI commands for ingesting, inspecting, generating, and evaluating.

Success means:

- Higher persona-match score than a generic baseline.
- Lower exact-copy rate than naive high-order Markov generation.
- Stable memory updates across live conversations.
- No live conversation enters training data unless config and approval policy allow it.
- Evaluation reports are reproducible from a saved config.

### Phase 2: Persona Distillation and Retrieval-Augmented Generation

Goal: move from local sequence mimicry toward adaptive personalized responses.

Expected features:

- Structured persona profile extraction.
- Retrieval over user memories and source examples.
- Response composer that combines retrieved memories, persona profile, and Jugemu suggestions.
- More robust privacy redaction and sensitive-data controls.
- Automatic eval reports comparing generated text to held-out user text.

Success means:

- Generated responses become more persona-consistent without copying source passages.
- The system can explain which memories or style features influenced a response.
- Privacy-leakage checks remain below a defined threshold.
- Held-out evaluation improves over Phase 1.

### Phase 3: Adversarial Arena

Goal: test whether agent competition can improve style fidelity, robustness, and safety.

Expected features:

- Imitator agent that tries to mimic the target user.
- Discriminator agent that distinguishes real user text from generated text.
- Adversary agent that probes inconsistency, privacy leakage, and style drift.
- Editor agent that rewrites weak outputs.
- Judge agent that scores human-likeness, persona-likeness, factuality, and safety.

Success means:

- The discriminator becomes less accurate over time on held-out evaluations.
- The adversary finds regressions that normal tests miss.
- Editor-improved outputs score better without increasing copy rate.
- Arena-generated examples are labeled as synthetic and do not pollute human-origin training data.

### Phase 4: Adapter Training and LoRA

Goal: introduce neural-weight adaptation without compromising provenance, privacy, or reproducibility.

Expected features:

- LoRA or other lightweight adapter training.
- Training queue built from explicitly approved examples.
- Train/validation/test splits based on time and source.
- Adapter versioning and rollback.
- Comparison between retrieval-only, Jugemu-only, and adapter-assisted generation.

Success means:

- Adapter-assisted generation improves persona-match and human-likeness scores over retrieval-only baselines.
- Exact-copy rate does not rise beyond the allowed threshold.
- Privacy-leakage checks do not regress.
- Catastrophic forgetting and model-collapse indicators are tracked.
- Every adapter can be traced to source data, config, and eval results.

### Phase 5: Useful CLI/TUI Chatbot

Goal: make Seuss practically useful as a local personalized chat system.

Expected features:

- Conversational CLI/TUI.
- Inspectable memory.
- User-controlled memory edits and deletion.
- Training approval review flow.
- Eval summary dashboard in terminal form.
- Multiple persona profiles or projects.

Success means:

- Users can comfortably operate Seuss without touching internals.
- The chatbot adapts over time in observable, reversible ways.
- Memory and training behavior are understandable and auditable.
- Research metrics remain visible rather than hidden behind product UX.

## Evaluation Metrics

Phase 1 should start with simple, reproducible metrics:

- Persona-match score.
- Real-vs-generated authorship discrimination.
- Exact-copy rate against source corpus.
- Repetition/diversity score.
- Privacy-leakage check.
- Held-out perplexity or sequence likelihood where applicable.
- Stability across repeated adaptation cycles.

Later phases should add:

- Human A/B authorship tests.
- LLM-as-judge comparisons with bias controls.
- Adversarial consistency tests.
- Memory attribution quality.
- Adapter-vs-retrieval ablations.
- Model-collapse indicators for synthetic-data loops.

## Research Risks

Key risks to track from the start:

- Model collapse from recursive synthetic training.
- Memorization and source passage leakage.
- Privacy leakage from live conversations.
- Persona drift after repeated adaptation.
- Catastrophic forgetting after adapter training.
- Evaluation gaming by judge or discriminator agents.
- Confusing adaptation with impersonation.

## References

- Shumailov et al., "AI models collapse when trained on recursively generated data", Nature, 2024: https://www.nature.com/articles/s41586-024-07566-y
- Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena", 2023: https://arxiv.org/abs/2306.05685
- Jones and Bergen, "Large Language Models Pass the Turing Test", 2025: https://arxiv.org/abs/2503.23674
- TuringBench benchmark environment: https://turingbench.ist.psu.edu/human.html
- Gao et al., "A Survey of Self-Evolving Agents", 2025: https://arxiv.org/abs/2507.21046
- Allison Parrish, "N-grams and Markov chains": https://www.decontextualize.com/teaching/rwet/n-grams-and-markov-chains/
