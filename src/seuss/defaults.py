DEFAULT_CONFIG_YAML = """project:
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
    anti_copy_ngram: 12
    backoff: true

evaluation:
  exact_copy_ngram: 12
  heldout_required: true
  report_path: ./.seuss/evals
"""
