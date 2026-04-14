#!/usr/bin/env python3
"""Run poor-cli against SWE-bench Lite and record reproducible cost telemetry."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable


DATASET_NAME = "princeton-nlp/SWE-bench_Lite"
DATASET_REVISION = "6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2"
DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_SEED = 0
COST_CONFIRMATION = "RUN SWE BENCH"
REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="bench/swe_bench_lite/run.py")
    parser.add_argument("--provider", default=os.getenv("POOR_CLI_BENCH_PROVIDER", DEFAULT_PROVIDER))
    parser.add_argument("--model", default=os.getenv("POOR_CLI_BENCH_MODEL", DEFAULT_MODEL))
    parser.add_argument("--dataset-name", default=DATASET_NAME)
    parser.add_argument("--dataset-revision", default=DATASET_REVISION)
    parser.add_argument("--split", default="test")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--run-id")
    parser.add_argument("--task-subset-filter", help="Regex matched against instance_id")
    parser.add_argument("--instance-id", action="append", default=[], help="Specific SWE-bench instance; repeatable")
    parser.add_argument("--limit", type=int, help="Optional smoke subset size")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle selected tasks using --seed")
    parser.add_argument("--results-dir", default="bench/swe_bench_lite/results")
    parser.add_argument("--work-dir", default=".poor-cli/bench/swe_bench_lite/worktrees")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--permission-mode", default="acceptEdits")
    parser.add_argument("--sandbox-preset", default="workspace-write")
    parser.add_argument("--auto-approve", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--confirm-cost", action="store_true", help="Acknowledge API/Docker cost before generation")
    parser.add_argument("--no-evaluate", action="store_true", help="Skip official SWE-bench Docker evaluation")
    parser.add_argument("--eval-max-workers", type=int, default=8)
    parser.add_argument("--keep-worktrees", action="store_true")
    return parser.parse_args(argv)


def utc_run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_tasks(dataset_name: str, split: str, revision: str) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit(
            "Missing bench deps. Run: python -m pip install -r bench/swe_bench_lite/requirements.txt"
        ) from exc
    return [dict(row) for row in load_dataset(dataset_name, split=split, revision=revision)]


def select_tasks(
    tasks: Iterable[dict[str, Any]],
    *,
    instance_ids: list[str],
    task_subset_filter: str | None,
    limit: int | None,
    shuffle: bool,
    seed: int,
) -> list[dict[str, Any]]:
    selected = list(tasks)
    if instance_ids:
        wanted = set(instance_ids)
        selected = [task for task in selected if str(task.get("instance_id")) in wanted]
    if task_subset_filter:
        pattern = re.compile(task_subset_filter)
        selected = [task for task in selected if pattern.search(str(task.get("instance_id", "")))]
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(selected)
    if limit is not None:
        selected = selected[: max(0, limit)]
    return selected


def benchmark_prompt(task: dict[str, Any]) -> str:
    return str(task.get("problem_statement") or "")


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def checkout_task_repo(task: dict[str, Any], task_dir: Path) -> None:
    repo = str(task["repo"])
    base_commit = str(task["base_commit"])
    if task_dir.exists():
        shutil.rmtree(task_dir)
    task_dir.parent.mkdir(parents=True, exist_ok=True)
    clone = run_command(["git", "clone", "--quiet", f"https://github.com/{repo}.git", str(task_dir)])
    if clone.returncode != 0:
        raise RuntimeError(clone.stderr.strip() or clone.stdout.strip() or f"git clone failed for {repo}")
    checkout = run_command(["git", "checkout", "--quiet", base_commit], cwd=task_dir)
    if checkout.returncode != 0:
        raise RuntimeError(checkout.stderr.strip() or checkout.stdout.strip() or f"git checkout failed for {base_commit}")


def parse_exec_json(stdout: str) -> dict[str, Any]:
    try:
        parsed = json.loads(stdout)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def cost_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cost = payload.get("cost") if isinstance(payload.get("cost"), dict) else {}
    return {
        "input_tokens": int(cost.get("input_tokens") or cost.get("inputTokens") or 0),
        "output_tokens": int(cost.get("output_tokens") or cost.get("outputTokens") or 0),
        "total_tokens": int(cost.get("total_tokens") or cost.get("totalTokens") or 0),
        "cost_usd": float(cost.get("estimated_cost_usd") or cost.get("estimatedCost") or 0.0),
        "cache_read_input_tokens": int(cost.get("cache_read_input_tokens") or cost.get("cacheReadInputTokens") or 0),
        "cache_creation_input_tokens": int(
            cost.get("cache_creation_input_tokens") or cost.get("cacheCreationInputTokens") or 0
        ),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def git_diff(task_dir: Path) -> str:
    result = run_command(["git", "diff", "--binary"], cwd=task_dir)
    return result.stdout if result.returncode == 0 else ""


def git_status(task_dir: Path) -> str:
    result = run_command(["git", "status", "--short"], cwd=task_dir)
    return result.stdout if result.returncode == 0 else ""


def git_commit() -> str:
    result = run_command(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)
    return result.stdout.strip() if result.returncode == 0 else ""


def run_task(task: dict[str, Any], args: argparse.Namespace, run_dir: Path, work_dir: Path) -> dict[str, Any]:
    instance_id = str(task["instance_id"])
    task_dir = work_dir / instance_id
    task_out = run_dir / instance_id
    task_out.mkdir(parents=True, exist_ok=True)
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    wall_start = time.monotonic()
    checkout_error = ""
    timed_out = False
    timeout_stdout = ""
    timeout_stderr = ""
    exec_result: subprocess.CompletedProcess[str] | None = None
    payload: dict[str, Any] = {}
    patch = ""
    status = ""
    try:
        checkout_task_repo(task, task_dir)
        prompt = benchmark_prompt(task)
        if not prompt:
            raise RuntimeError("empty SWE-bench problem_statement")
        command = [
            args.python,
            "-m",
            "poor_cli",
            "exec",
            "--prompt",
            prompt,
            "--output-format",
            "json",
            "--provider",
            args.provider,
            "--model",
            args.model,
            "--permission-mode",
            args.permission_mode,
            "--sandbox-preset",
            args.sandbox_preset,
        ]
        if args.auto_approve:
            command.append("--auto-approve")
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = str(args.seed)
        env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
        exec_result = run_command(command, cwd=task_dir, timeout=args.timeout_seconds, env=env)
        payload = parse_exec_json(exec_result.stdout)
        patch = git_diff(task_dir)
        status = git_status(task_dir)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        timeout_stdout = exc.stdout or ""
        timeout_stderr = exc.stderr or ""
        checkout_error = f"poor-cli exec timed out after {args.timeout_seconds}s"
        if task_dir.exists():
            patch = git_diff(task_dir)
            status = git_status(task_dir)
    except Exception as exc:
        checkout_error = str(exc)
    finally:
        if task_dir.exists() and not args.keep_worktrees:
            shutil.rmtree(task_dir)
    stdout = exec_result.stdout if exec_result is not None else timeout_stdout
    stderr = exec_result.stderr if exec_result is not None else timeout_stderr or checkout_error
    (task_out / "stdout.txt").write_text(stdout, encoding="utf-8")
    (task_out / "stderr.txt").write_text(stderr, encoding="utf-8")
    cost = cost_from_payload(payload)
    record = {
        "instance_id": instance_id,
        "repo": task.get("repo"),
        "base_commit": task.get("base_commit"),
        "model": args.model,
        "provider": args.provider,
        "dataset_name": args.dataset_name,
        "dataset_revision": args.dataset_revision,
        "seed": args.seed,
        "started_at": started_at,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "wall_time_seconds": round(time.monotonic() - wall_start, 3),
        "exit_code": exec_result.returncode if exec_result is not None else 124 if timed_out else 1,
        "cost": cost,
        "git_status": status,
        "patch_bytes": len(patch.encode("utf-8")),
        "stdout_path": str(task_out / "stdout.txt"),
        "stderr_path": str(task_out / "stderr.txt"),
        "error": checkout_error,
    }
    write_json(task_out / "result.json", record)
    append_jsonl(run_dir / "task_results.jsonl", record)
    append_jsonl(
        run_dir / "predictions.jsonl",
        {"instance_id": instance_id, "model_name_or_path": args.model, "model_patch": patch},
    )
    return record


def summarize(records: list[dict[str, Any]], args: argparse.Namespace, run_id: str) -> dict[str, Any]:
    costs = [float(record.get("cost", {}).get("cost_usd", 0.0) or 0.0) for record in records]
    times = [float(record.get("wall_time_seconds", 0.0) or 0.0) for record in records]
    total_tokens = [int(record.get("cost", {}).get("total_tokens", 0) or 0) for record in records]
    return {
        "run_id": run_id,
        "benchmark": "SWE-bench Lite",
        "dataset_name": args.dataset_name,
        "dataset_revision": args.dataset_revision,
        "split": args.split,
        "provider": args.provider,
        "model": args.model,
        "seed": args.seed,
        "task_count": len(records),
        "completed_exec_count": sum(1 for record in records if int(record.get("exit_code", 1)) == 0),
        "total_cost_usd": round(sum(costs), 6),
        "mean_cost_usd": round(sum(costs) / len(costs), 6) if costs else 0.0,
        "total_tokens": sum(total_tokens),
        "mean_tokens": round(sum(total_tokens) / len(total_tokens), 2) if total_tokens else 0.0,
        "mean_wall_time_seconds": round(sum(times) / len(times), 3) if times else 0.0,
        "p50_wall_time_seconds": percentile(times, 50),
        "p95_wall_time_seconds": percentile(times, 95),
        "official_evaluation": {},
    }


def percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * (pct / 100))
    return round(ordered[index], 3)


def confirm_cost(args: argparse.Namespace, task_count: int) -> None:
    warning_text = (
        f"COST WARNING: this will run poor-cli on {task_count} SWE-bench Lite task(s) "
        f"with provider={args.provider} model={args.model}. This can incur model API charges "
        "and Docker evaluation costs."
    )
    if args.confirm_cost:
        print(warning_text, file=sys.stderr)
        return
    warning = f"{warning_text} Type RUN SWE BENCH to continue: "
    if not sys.stdin.isatty():
        raise SystemExit(f"{warning}\nrerun with --confirm-cost to acknowledge.")
    if input(warning).strip() != COST_CONFIRMATION:
        raise SystemExit("aborted")


def run_official_evaluation(args: argparse.Namespace, run_dir: Path, run_id: str) -> dict[str, Any]:
    command = [
        args.python,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        args.dataset_name,
        "--predictions_path",
        str((run_dir / "predictions.jsonl").resolve()),
        "--max_workers",
        str(args.eval_max_workers),
        "--run_id",
        run_id,
    ]
    started = time.monotonic()
    result = run_command(command, cwd=run_dir)
    (run_dir / "evaluation_stdout.txt").write_text(result.stdout, encoding="utf-8")
    (run_dir / "evaluation_stderr.txt").write_text(result.stderr, encoding="utf-8")
    discovered = sorted(run_dir.rglob("results.json"))
    payload: dict[str, Any] = {}
    if discovered:
        try:
            payload = json.loads(discovered[-1].read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    return {
        "exit_code": result.returncode,
        "wall_time_seconds": round(time.monotonic() - started, 3),
        "results_json": str(discovered[-1]) if discovered else "",
        "results": payload,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    random.seed(args.seed)
    tasks = select_tasks(
        load_tasks(args.dataset_name, args.split, args.dataset_revision),
        instance_ids=args.instance_id,
        task_subset_filter=args.task_subset_filter,
        limit=args.limit,
        shuffle=args.shuffle,
        seed=args.seed,
    )
    confirm_cost(args, len(tasks))
    run_id = args.run_id or utc_run_id()
    run_dir = Path(args.results_dir) / run_id
    work_dir = Path(args.work_dir).resolve()
    if run_dir.exists():
        raise SystemExit(f"run dir already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    write_json(
        run_dir / "environment.json",
        {
            "python": sys.version,
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "repo_root": str(REPO_ROOT),
            "commit": git_commit(),
            "dataset_name": args.dataset_name,
            "dataset_revision": args.dataset_revision,
            "seed": args.seed,
            "provider": args.provider,
            "model": args.model,
            "permission_mode": args.permission_mode,
            "sandbox_preset": args.sandbox_preset,
            "auto_approve": args.auto_approve,
        },
    )
    records = []
    for index, task in enumerate(tasks, start=1):
        print(f"[{index}/{len(tasks)}] {task.get('instance_id')}", flush=True)
        records.append(run_task(task, args, run_dir, work_dir))
    summary = summarize(records, args, run_id)
    if not args.no_evaluate:
        summary["official_evaluation"] = run_official_evaluation(args, run_dir, run_id)
    write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
