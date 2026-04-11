"""
Benchmark: text-based vs latent inter-agent communication.

Compares token counts, wall-clock time, and output quality between
standard text round-trips and LatentMAS-style hidden-state passing.

Usage:
    python -m tests.bench_latent_communication --model Qwen/Qwen2.5-3B
    python -m tests.bench_latent_communication --model Qwen/Qwen2.5-3B --device mps
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import torch
    from poor_cli.latent_communication import (
        load_model, LatentAgentOrchestrator, is_latent_compatible, LatentBenchmark,
    )
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    IMPORT_ERR = str(e)

BENCH_TASKS = [
    # math
    "What is 347 * 29?",
    "If a train travels 120km in 1.5 hours, what is its speed in m/s?",
    "Solve: 2x + 5 = 17",
    "What is the sum of the first 20 prime numbers?",
    "A rectangle has perimeter 40 and area 96. What are its dimensions?",
    # code
    "Write a Python function to check if a string is a palindrome.",
    "Write a function that returns the nth Fibonacci number iteratively.",
    "Implement binary search on a sorted list in Python.",
    "Write a Python function to flatten a nested list.",
    "Write a function to find the GCD of two numbers.",
    # planning
    "Plan the steps to deploy a Django app to AWS EC2.",
    "Plan how to migrate a SQLite database to PostgreSQL.",
    "Plan the steps to set up CI/CD with GitHub Actions for a Python project.",
    "Plan how to implement rate limiting in a REST API.",
    "Plan the steps to add OAuth2 authentication to a web app.",
    # qa
    "What are the SOLID principles in software engineering?",
    "Explain the difference between TCP and UDP.",
    "What is the CAP theorem and why does it matter?",
    "Explain how garbage collection works in Python.",
    "What is the difference between a process and a thread?",
]


def print_comparison(latent: LatentBenchmark, text: LatentBenchmark, task: str):
    token_saved = 1 - (latent.output_tokens / max(text.output_tokens, 1))
    speedup = text.wall_time_s / max(latent.wall_time_s, 0.001)
    print(f"  Task: {task[:60]}...")
    print(f"    Text:   {text.output_tokens:5d} out tokens, {text.wall_time_s:6.2f}s")
    print(f"    Latent: {latent.output_tokens:5d} out tokens, {latent.wall_time_s:6.2f}s")
    print(f"    Savings: {token_saved*100:.1f}% tokens, {speedup:.2f}x speedup")
    print()


async def run_benchmark(model_name: str, device: str, latent_steps: int, max_tasks: int):
    print(f"Loading model: {model_name} on {device}...")
    t0 = time.monotonic()
    model, tokenizer = load_model(model_name, device=device)
    print(f"Model loaded in {time.monotonic() - t0:.1f}s")
    if device == "cuda":
        vram_gb = torch.cuda.max_memory_allocated() / 1e9
        print(f"VRAM used: {vram_gb:.1f}GB")
    orch = LatentAgentOrchestrator(model, tokenizer, latent_steps=latent_steps, device=device)
    tasks = BENCH_TASKS[:max_tasks]
    results = []
    print(f"\nRunning {len(tasks)} tasks (latent_steps={latent_steps})...\n")
    for i, task in enumerate(tasks):
        print(f"[{i+1}/{len(tasks)}]")
        try:
            _, bench_latent = await orch.run_pipeline(task, max_new_tokens=256)
            _, bench_text = await orch.run_text_baseline(task, max_new_tokens=256)
            print_comparison(bench_latent, bench_text, task)
            results.append({
                "task": task,
                "latent": {"output_tokens": bench_latent.output_tokens, "wall_time_s": bench_latent.wall_time_s, "latent_steps": bench_latent.latent_steps},
                "text": {"output_tokens": bench_text.output_tokens, "wall_time_s": bench_text.wall_time_s},
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"task": task, "error": str(e)})
    # summary
    valid = [r for r in results if "error" not in r]
    if valid:
        avg_token_save = sum(1 - r["latent"]["output_tokens"] / max(r["text"]["output_tokens"], 1) for r in valid) / len(valid)
        avg_speedup = sum(r["text"]["wall_time_s"] / max(r["latent"]["wall_time_s"], 0.001) for r in valid) / len(valid)
        print("=" * 60)
        print(f"SUMMARY ({len(valid)}/{len(tasks)} tasks completed)")
        print(f"  Avg token savings: {avg_token_save*100:.1f}%")
        print(f"  Avg speedup:       {avg_speedup:.2f}x")
        print(f"  Model:             {model_name}")
        print(f"  Latent steps:      {latent_steps}")
        print("=" * 60)
    out_path = Path(__file__).parent / "bench_latent_results.json"
    with open(out_path, "w") as f:
        json.dump({"model": model_name, "device": device, "latent_steps": latent_steps, "results": results}, f, indent=2)
    print(f"\nResults saved to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark latent vs text agent communication")
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B", help="HF model name")
    parser.add_argument("--device", default="cuda", help="cuda, mps, or cpu")
    parser.add_argument("--latent-steps", type=int, default=20, help="latent reasoning steps per agent")
    parser.add_argument("--max-tasks", type=int, default=20, help="max tasks to run")
    args = parser.parse_args()
    if not HAS_DEPS:
        print(f"Missing dependencies: {IMPORT_ERR}")
        print("Install: pip install torch transformers accelerate")
        sys.exit(1)
    compat = is_latent_compatible()
    if not compat["feasible"]:
        print(f"Environment not compatible: {compat['reason']}")
        sys.exit(1)
    asyncio.run(run_benchmark(args.model, args.device, args.latent_steps, args.max_tasks))


if __name__ == "__main__":
    main()
