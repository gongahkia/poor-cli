from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from seuss.defaults import DEFAULT_CONFIG_YAML
from seuss.provenance import validate_provenance

DEFAULT_CONFIG_PATH = Path("seuss.yaml")


class ConfigError(RuntimeError):
    pass


def write_default_config(path: Path, force: bool = False) -> None:
    if path.exists() and not force:
        raise ConfigError(f"Config already exists at {path}. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(
            f"Config not found at {path}. Run 'seuss init' or pass --config <path>."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping.")
    validate_config(raw)
    return raw


def _expect_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be a mapping")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(f"{path} must be a list")
    return value


def _expect_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} must be a non-empty string")
    return value


def _expect_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{path} must be a boolean")
    return value


def _expect_int(value: Any, path: str, minimum: int | None = None) -> int:
    if not isinstance(value, int):
        raise ConfigError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{path} must be >= {minimum}")
    return value


def _expect_float(value: Any, path: str, minimum: float | None = None) -> float:
    if not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be a number")
    value_f = float(value)
    if minimum is not None and value_f < minimum:
        raise ConfigError(f"{path} must be >= {minimum}")
    return value_f


def _validate_source(source: dict[str, Any], idx: int) -> None:
    prefix = f"sources[{idx}]"
    name = _expect_str(source.get("name"), f"{prefix}.name")
    src_type = _expect_str(source.get("type"), f"{prefix}.type")
    _expect_str(source.get("path"), f"{prefix}.path")
    _expect_bool(source.get("enabled", True), f"{prefix}.enabled")
    provenance = source.get("provenance", "human_original")
    validate_provenance(provenance)

    allowed_source_types = {"directory", "jsonl"}
    if src_type not in allowed_source_types:
        raise ConfigError(f"{prefix}.type must be one of {sorted(allowed_source_types)}")

    if src_type == "directory":
        include = source.get("include", ["*.txt", "*.md"])
        include_list = _expect_list(include, f"{prefix}.include")
        if not include_list:
            raise ConfigError(f"{prefix}.include must not be empty")
        for i, pattern in enumerate(include_list):
            _expect_str(pattern, f"{prefix}.include[{i}]")

    if src_type == "jsonl":
        if "text_field" in source:
            _expect_str(source["text_field"], f"{prefix}.text_field")
        if "speaker_field" in source:
            _expect_str(source["speaker_field"], f"{prefix}.speaker_field")
        if "timestamp_field" in source:
            _expect_str(source["timestamp_field"], f"{prefix}.timestamp_field")

    # Prevent accidental duplicate names across source registry.
    if name.startswith("."):
        raise ConfigError(f"{prefix}.name may not start with '.'")


def validate_config(config: dict[str, Any]) -> None:
    required_roots = [
        "project",
        "sources",
        "privacy",
        "segmentation",
        "splits",
        "adaptation",
        "generation",
        "evaluation",
    ]
    for key in required_roots:
        if key not in config:
            raise ConfigError(f"Missing required config section: {key}")

    project = _expect_mapping(config["project"], "project")
    _expect_str(project.get("name"), "project.name")
    _expect_str(project.get("workspace"), "project.workspace")

    sources = _expect_list(config["sources"], "sources")
    if not sources:
        raise ConfigError("sources must contain at least one source")
    seen_source_names: set[str] = set()
    for idx, source in enumerate(sources):
        source_map = _expect_mapping(source, f"sources[{idx}]")
        _validate_source(source_map, idx)
        source_name = source_map["name"]
        if source_name in seen_source_names:
            raise ConfigError(f"Duplicate source name: {source_name}")
        seen_source_names.add(source_name)

    privacy = _expect_mapping(config["privacy"], "privacy")
    redact = _expect_mapping(privacy.get("redact"), "privacy.redact")
    _expect_bool(redact.get("emails", True), "privacy.redact.emails")
    _expect_bool(redact.get("phone_numbers", True), "privacy.redact.phone_numbers")
    _expect_bool(redact.get("urls", False), "privacy.redact.urls")
    custom_patterns = _expect_list(
        redact.get("custom_patterns", []), "privacy.redact.custom_patterns"
    )
    for i, pattern in enumerate(custom_patterns):
        _expect_str(pattern, f"privacy.redact.custom_patterns[{i}]")

    segmentation = _expect_mapping(config["segmentation"], "segmentation")
    for bool_key in ("paragraph", "sentence", "phrase", "word", "character"):
        _expect_bool(segmentation.get(bool_key, True), f"segmentation.{bool_key}")
    min_chars = _expect_int(segmentation.get("min_fragment_chars", 3), "segmentation.min_fragment_chars", minimum=1)
    max_chars = _expect_int(segmentation.get("max_fragment_chars", 2000), "segmentation.max_fragment_chars", minimum=1)
    if min_chars > max_chars:
        raise ConfigError("segmentation.min_fragment_chars must be <= segmentation.max_fragment_chars")

    splits = _expect_mapping(config["splits"], "splits")
    strategy = _expect_str(splits.get("strategy", "time"), "splits.strategy")
    if strategy not in {"time", "hash"}:
        raise ConfigError("splits.strategy must be one of ['hash', 'time']")
    train_ratio = _expect_float(splits.get("train_ratio", 0.8), "splits.train_ratio", minimum=0.0)
    eval_ratio = _expect_float(splits.get("eval_ratio", 0.2), "splits.eval_ratio", minimum=0.0)
    if train_ratio <= 0:
        raise ConfigError("splits.train_ratio must be > 0")
    if eval_ratio <= 0:
        raise ConfigError("splits.eval_ratio must be > 0")
    if train_ratio + eval_ratio > 1.000001:
        raise ConfigError("splits.train_ratio + splits.eval_ratio must be <= 1")
    _expect_int(splits.get("seed", 42), "splits.seed")

    adaptation = _expect_mapping(config["adaptation"], "adaptation")
    live_memory = _expect_mapping(adaptation.get("live_memory"), "adaptation.live_memory")
    _expect_bool(live_memory.get("enabled", True), "adaptation.live_memory.enabled")
    _expect_bool(
        live_memory.get("summarize_after_each_turn", True),
        "adaptation.live_memory.summarize_after_each_turn",
    )

    live_training = _expect_mapping(
        adaptation.get("live_training_data"), "adaptation.live_training_data"
    )
    _expect_bool(
        live_training.get("enabled", False), "adaptation.live_training_data.enabled"
    )
    _expect_bool(
        live_training.get("require_explicit_approval", True),
        "adaptation.live_training_data.require_explicit_approval",
    )
    _expect_str(
        live_training.get("queue_path", "./.seuss/training_queue.jsonl"),
        "adaptation.live_training_data.queue_path",
    )

    auto_training = _expect_mapping(
        adaptation.get("auto_training_data"), "adaptation.auto_training_data"
    )
    _expect_bool(
        auto_training.get("enabled", False), "adaptation.auto_training_data.enabled"
    )
    _expect_float(
        auto_training.get("min_quality_score", 0.8),
        "adaptation.auto_training_data.min_quality_score",
        minimum=0.0,
    )
    _expect_bool(
        auto_training.get("allow_ai_generated", False),
        "adaptation.auto_training_data.allow_ai_generated",
    )

    generation = _expect_mapping(config["generation"], "generation")
    default_level = _expect_str(generation.get("default_level", "hybrid"), "generation.default_level")
    if default_level not in {"character", "word", "phrase", "hybrid"}:
        raise ConfigError(
            "generation.default_level must be one of ['character', 'hybrid', 'phrase', 'word']"
        )
    _expect_int(generation.get("max_tokens", 120), "generation.max_tokens", minimum=1)
    _expect_float(generation.get("temperature", 0.8), "generation.temperature", minimum=0.0)
    _expect_int(generation.get("seed", 42), "generation.seed")

    jugemu = _expect_mapping(generation.get("jugemu"), "generation.jugemu")
    _expect_int(jugemu.get("character_order", 5), "generation.jugemu.character_order", minimum=1)
    _expect_int(jugemu.get("word_order", 3), "generation.jugemu.word_order", minimum=1)
    _expect_int(jugemu.get("phrase_order", 2), "generation.jugemu.phrase_order", minimum=1)
    _expect_int(jugemu.get("sentence_order", 1), "generation.jugemu.sentence_order", minimum=1)
    _expect_int(jugemu.get("motif_order", 2), "generation.jugemu.motif_order", minimum=1)
    _expect_int(jugemu.get("anti_copy_ngram", 12), "generation.jugemu.anti_copy_ngram", minimum=1)
    _expect_bool(jugemu.get("backoff", True), "generation.jugemu.backoff")

    evaluation = _expect_mapping(config["evaluation"], "evaluation")
    _expect_int(
        evaluation.get("exact_copy_ngram", 12),
        "evaluation.exact_copy_ngram",
        minimum=1,
    )
    _expect_bool(
        evaluation.get("heldout_required", True), "evaluation.heldout_required"
    )
    _expect_str(evaluation.get("report_path", "./.seuss/evals"), "evaluation.report_path")
    thresholds = _expect_mapping(
        evaluation.get("thresholds", {}),
        "evaluation.thresholds",
    )
    if "persona_match_min" in thresholds:
        _expect_float(
            thresholds["persona_match_min"], "evaluation.thresholds.persona_match_min", minimum=0.0
        )
    if "exact_copy_rate_max" in thresholds:
        _expect_float(
            thresholds["exact_copy_rate_max"], "evaluation.thresholds.exact_copy_rate_max", minimum=0.0
        )
    if "repetition_score_max" in thresholds:
        _expect_float(
            thresholds["repetition_score_max"], "evaluation.thresholds.repetition_score_max", minimum=0.0
        )
    if "privacy_leak_count_max" in thresholds:
        _expect_int(
            thresholds["privacy_leak_count_max"], "evaluation.thresholds.privacy_leak_count_max", minimum=0
        )


def resolve_workspace(config: dict[str, Any], config_path: Path) -> Path:
    workspace_value = config.get("project", {}).get("workspace", "./.seuss")
    workspace = Path(workspace_value)
    if not workspace.is_absolute():
        workspace = (config_path.parent / workspace).resolve()
    return workspace


def resolve_path(value: str, config_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()
