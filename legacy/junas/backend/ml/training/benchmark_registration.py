from __future__ import annotations

from typing import Any

import httpx


def register_lexglue_score(
    api_base_url: str,
    model_name: str,
    run_name: str,
    task: str,
    micro_f1: float,
    macro_f1: float | None = None,
    metadata: dict[str, Any] | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/api/v1/benchmarks/register"
    payload: dict[str, Any] = {
        "model_name": model_name,
        "run_name": run_name,
        "task": task,
        "micro_f1": float(micro_f1),
    }
    if macro_f1 is not None:
        payload["macro_f1"] = float(macro_f1)
    if metadata:
        payload["metadata"] = metadata

    response = httpx.post(url, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError("Unexpected response from benchmark registration endpoint")
    return body
