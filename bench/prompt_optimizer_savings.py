#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poor_cli.adaptive_budget import AdaptiveBudgetController
from poor_cli.prompt_optimizer import PromptOptimizer
from poor_cli.prompts import build_tool_calling_system_instruction
from poor_cli.token_budget_controller import TokenBudgetState
from poor_cli.token_counter import get_token_counter


def main() -> int:
    ctl = AdaptiveBudgetController()
    ctl._rewards.extend([0.9, 0.8, 0.9, 0.85, 0.9, 0.82])
    ctl.decide(TokenBudgetState(task_complexity=0.2))
    optimizer = PromptOptimizer(ctl)
    prompts = [f"small maintenance prompt {idx}" for idx in range(50)]
    full_tokens = 0
    optimized_tokens = 0
    counter = get_token_counter()
    for _prompt in prompts:
        full = build_tool_calling_system_instruction(str(REPO_ROOT))
        optimized = build_tool_calling_system_instruction(
            str(REPO_ROOT),
            prompt_optimizer=optimizer,
            task_complexity=0.2,
        )
        full_tokens += counter.count(full).count
        optimized_tokens += counter.count(optimized).count
    reduction = (full_tokens - optimized_tokens) / max(1, full_tokens)
    payload = {
        "fullTokens": full_tokens,
        "optimizedTokens": optimized_tokens,
        "reduction": round(reduction, 4),
        "threshold": 0.25,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if reduction >= 0.25 else 1


if __name__ == "__main__":
    raise SystemExit(main())
