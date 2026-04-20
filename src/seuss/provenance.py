ALLOWED_PROVENANCE = {
    "human_original",
    "human_edited",
    "conversation_live",
    "memory_summary",
    "ai_generated",
    "ai_edited",
    "synthetic_adversarial",
    "synthetic_selfplay",
}


def validate_provenance(value: str) -> None:
    if value not in ALLOWED_PROVENANCE:
        raise ValueError(
            f"Invalid provenance label '{value}'. Allowed: {sorted(ALLOWED_PROVENANCE)}"
        )
