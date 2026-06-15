from __future__ import annotations

from pathlib import Path

import pytest

from poor_cli.config import add_provider, empty_config, provider_preset, save_repo_config
from poor_cli.cost import BudgetExceeded, BudgetLedger, Price, estimate_cost
from poor_cli.providers import ProviderRequest, ProviderResponse
from poor_cli.store import RunStore


def test_cost_math_handles_cached_tokens() -> None:
    price = Price(input_per_million=2.0, cached_input_per_million=0.5, output_per_million=10.0)

    assert estimate_cost(1_000_000, 250_000, 100_000, 0, price) == 2.625


def test_budget_unknown_pricing_warns_unless_strict(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(
        user_goal="goal",
        repo_path=tmp_path,
        git_commit_start="abc",
        mode="balanced",
        budget={"max_usd": 0.01, "strict_pricing": False},
    )
    request = ProviderRequest(provider="vllm", model="qwen", prompt="hello")

    BudgetLedger.load(store, run_id).check_provider_request(request, request.request_hash())

    assert any(event["type"] == "budget.warning" and event["payload"]["code"] == "unknown_pricing" for event in store.list_events(run_id))

    strict_id = store.create_run(
        user_goal="goal",
        repo_path=tmp_path,
        git_commit_start="abc",
        mode="balanced",
        budget={"max_usd": 0.01, "strict_pricing": True},
    )
    with pytest.raises(BudgetExceeded):
        BudgetLedger.load(store, strict_id).check_provider_request(request, request.request_hash())
    store.close()


def test_budget_ledger_records_usage_and_thresholds(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(
        user_goal="goal",
        repo_path=tmp_path,
        git_commit_start="abc",
        mode="balanced",
        budget={"max_usd": 0.01},
    )
    request = ProviderRequest(provider="openai", model="gpt-5.5", prompt="hello")
    response = ProviderResponse(
        provider="openai",
        model="gpt-5.5",
        content="done",
        raw={"usage": {"input_tokens": 1000, "output_tokens": 1000, "input_tokens_details": {"cached_tokens": 500}}},
    )

    ledger = BudgetLedger.load(store, run_id)
    ledger.check_provider_request(request, request.request_hash())
    ledger.record_provider_response(request, request.request_hash(), response)

    payload = store.artifact_payload(store.list_artifacts(run_id, "budget.ledger")[-1]["artifact_id"])
    assert b"poor-cli-budget-ledger-v1" in payload
    assert any(event["type"] == "budget.entry" for event in store.list_events(run_id))
    assert any(event["type"] == "budget.warning" and event["payload"]["threshold"] == 100 for event in store.list_events(run_id))
    store.close()


def test_budget_ledger_uses_config_pricing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    profile = provider_preset("openai-compatible", profile_id="custom", model="custom-model", base_url="http://model.test")
    profile["custom"]["cost"] = {"input_per_million": 1.0, "output_per_million": 2.0, "cached_input_per_million": 0.25}
    save_repo_config(add_provider(config, "custom", profile["custom"]), tmp_path)
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    request = ProviderRequest(provider="openai-compatible", model="custom-model", prompt="hello")
    response = ProviderResponse(
        provider="openai-compatible",
        model="custom-model",
        content="done",
        raw={"usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 500}}},
    )

    ledger = BudgetLedger.load(store, run_id)
    ledger.record_provider_response(request, request.request_hash(), response)

    assert ledger.totals()["estimated_usd"] == 0.002625
    store.close()
