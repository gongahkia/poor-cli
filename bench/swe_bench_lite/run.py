#!/usr/bin/env python3
"""Run poor-cli v6 against a pinned SWE-bench Lite subset."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

DATASET_NAME = "princeton-nlp/SWE-bench_Lite"
DATASET_REVISION = ""
DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_AGENT = "claude"
DEFAULT_SEED = 0
COST_CONFIRMATION = "RUN SWE BENCH"
REPO_ROOT = Path(__file__).resolve().parents[2]
PINNED_MANIFEST = REPO_ROOT / "tests" / "fixtures" / "swe-lite-10" / "manifest.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="bench/swe_bench_lite/run.py")
    parser.add_argument("--provider", default=os.getenv("POOR_CLI_BENCH_PROVIDER", DEFAULT_PROVIDER))
    parser.add_argument("--model", default=os.getenv("POOR_CLI_BENCH_MODEL", DEFAULT_MODEL))
    parser.add_argument("--agent", choices=["claude", "codex", "generic"], default=os.getenv("POOR_CLI_BENCH_AGENT", DEFAULT_AGENT))
    parser.add_argument("--dataset-name", default=DATASET_NAME)
    parser.add_argument("--dataset-revision", default=DATASET_REVISION)
    parser.add_argument("--split", default="test")
    parser.add_argument("--manifest", default=str(PINNED_MANIFEST), help="Pinned SWE task manifest; use '' to disable.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--run-id")
    parser.add_argument("--task-subset-filter", help="Regex matched against instance_id")
    parser.add_argument("--instance-id", action="append", default=[], help="Specific SWE-bench instance; repeatable")
    parser.add_argument("--limit", type=int, help="Optional smoke subset size")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle selected tasks using --seed")
    parser.add_argument("--results-dir", default="bench/swe_bench_lite/results")
    parser.add_argument("--work-dir", default=".poor-cli/bench/swe_bench_lite/worktrees")
    parser.add_argument("--store-root", default=".poor-cli/bench/swe_bench_lite/stores")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--budget-usd", type=float, help="Pass a max model budget to poor-cli run.")
    parser.add_argument("--permission-mode", default="acceptEdits")
    parser.add_argument("--sandbox-preset", default="workspace-write")
    parser.add_argument("--auto-approve", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--confirm-cost", action="store_true", help="Acknowledge API/Docker cost before generation")
    parser.add_argument("--no-evaluate", action="store_true", help="Skip official SWE-bench Docker evaluation")
    parser.add_argument("--evaluate-existing-run", help="Run official evaluation for an existing run id or run directory.")
    parser.add_argument("--skip-replay-verify", action="store_true", help="Skip poor-cli offline replay verification")
    parser.add_argument("--eval-max-workers", type=int, default=8)
    parser.add_argument("--eval-timeout", type=int)
    parser.add_argument("--eval-namespace", default="swebench", help="SWE-bench image namespace; use 'none' to build locally.")
    parser.add_argument("--eval-force-rebuild", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--eval-cache-level", choices=["none", "base", "env", "instance"], default="env")
    parser.add_argument("--eval-clean", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--eval-isolated-docker-config", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--keep-worktrees", action="store_true")
    return parser.parse_args(argv)


def utc_run_id() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def load_tasks(dataset_name: str, split: str, revision: str) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("Missing bench deps. Run: python -m pip install -r bench/swe_bench_lite/requirements.txt") from exc
    kwargs: dict[str, Any] = {"split": split}
    if revision:
        kwargs["revision"] = revision
    return [dict(row) for row in load_dataset(dataset_name, **kwargs)]


def load_manifest(path: str) -> dict[str, Any] | None:
    if not path:
        return None
    manifest_path = Path(path)
    if not manifest_path.is_absolute():
        manifest_path = (Path.cwd() / manifest_path).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"manifest root must be object: {manifest_path}")
    return payload


def apply_manifest(tasks: Iterable[dict[str, Any]], manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if manifest is None:
        return list(tasks)
    indexed = {str(task.get("instance_id")): task for task in tasks}
    selected = []
    missing = []
    for expected in manifest.get("instances", []):
        if not isinstance(expected, dict):
            continue
        instance_id = str(expected.get("instance_id") or "")
        task = indexed.get(instance_id)
        if task is None:
            missing.append(instance_id)
            continue
        for key in ("repo", "base_commit"):
            wanted = str(expected.get(key) or "")
            actual = str(task.get(key) or "")
            if wanted and actual and wanted != actual:
                raise SystemExit(f"manifest mismatch for {instance_id} {key}: {actual} != {wanted}")
        selected.append(task)
    if missing:
        raise SystemExit(f"manifest instances missing from dataset: {', '.join(missing)}")
    return selected


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


def cost_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cost = payload.get("cost") if isinstance(payload.get("cost"), dict) else {}
    return {
        "input_tokens": int(cost.get("input_tokens") or cost.get("inputTokens") or 0),
        "output_tokens": int(cost.get("output_tokens") or cost.get("outputTokens") or 0),
        "total_tokens": int(cost.get("total_tokens") or cost.get("totalTokens") or 0),
        "cost_usd": float(cost.get("estimated_cost_usd") or cost.get("estimatedCost") or 0.0),
        "cache_read_input_tokens": int(cost.get("cache_read_input_tokens") or cost.get("cacheReadInputTokens") or 0),
        "cache_creation_input_tokens": int(cost.get("cache_creation_input_tokens") or cost.get("cacheCreationInputTokens") or 0),
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


def planner_payload(task: dict[str, Any], agent: str) -> dict[str, Any]:
    prompt = benchmark_prompt(task)
    return {
        "problem_summary": f"SWE-bench Lite task {task.get('instance_id')}",
        "architecture_assessment": "external benchmark repository",
        "assumptions": ["use grep-mode file navigation; do not use graph tools"],
        "risks": ["benchmark patch may need repository-specific test context"],
        "tasks": [
            {
                "title": f"Resolve {task.get('instance_id')}",
                "objective": prompt,
                "task_type": "implementation",
                "complexity": "high",
                "risk": "medium",
                "required_context": "repository files and issue statement",
                "dependencies": [],
                "suggested_agent": agent,
                "validation": ["run relevant tests from the issue statement when feasible"],
            }
        ],
        "validation_strategy": ["official SWE-bench Docker evaluation via predictions.jsonl"],
        "routing_strategy": agent,
        "estimated_cost": {"tokens": None, "usd": None},
        "requires_user_confirmation": True,
    }


def write_planner(path: Path, task: dict[str, Any], agent: str) -> Path:
    payload = planner_payload(task, agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"import json, sys\nsys.stdin.read()\nprint({json.dumps(payload)!r})\n", encoding="utf-8")
    return path


def extract_run_id(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("run_id:"):
            return line.split(":", 1)[1].strip()
    return ""


def poor_cli_env(args: argparse.Namespace, planner: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    src = str(REPO_ROOT / "src")
    env["PYTHONHASHSEED"] = str(args.seed)
    old_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not old_pythonpath else f"{src}{os.pathsep}{old_pythonpath}"
    if planner is not None:
        env["POOR_CLI_PLANNER_COMMAND"] = shlex.join([args.python, str(planner.resolve())])
    return env


def poor_cli_run_command(args: argparse.Namespace, store_dir: Path, prompt: str) -> list[str]:
    command = [
        args.python,
        "-m",
        "poor_cli",
        "--store-dir",
        str(store_dir),
        "run",
        prompt,
        "--yes",
    ]
    if args.budget_usd is not None:
        command.extend(["--budget", str(args.budget_usd)])
    return command


def run_replay_verify(args: argparse.Namespace, task_dir: Path, store_dir: Path, run_id: str) -> dict[str, Any]:
    if args.skip_replay_verify or not run_id:
        return {"verified": False, "returncode": 0, "stdout": "", "stderr": "", "trace_sha256": "", "command": []}
    command = [args.python, "-m", "poor_cli", "--offline", "--store-dir", str(store_dir), "replay", run_id, "--verify", "--json"]
    env = poor_cli_env(args)
    env["POOR_CLI_OFFLINE"] = "1"
    result = run_command(command, cwd=task_dir, env=env)
    trace = ""
    verified = False
    if result.returncode == 0:
        try:
            verification = json.loads(result.stdout)["verification"]
            verified = bool(verification["verified"])
            trace = str(verification.get("trace_sha256") or "")
        except (KeyError, json.JSONDecodeError, TypeError):
            verified = False
    return {
        "verified": verified,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "trace_sha256": trace,
        "command": command,
    }


def run_task(task: dict[str, Any], args: argparse.Namespace, run_dir: Path, work_dir: Path) -> dict[str, Any]:
    instance_id = str(task["instance_id"])
    task_dir = work_dir / instance_id
    task_out = run_dir / instance_id
    task_out.mkdir(parents=True, exist_ok=True)
    store_dir = Path(args.store_root).resolve() / run_dir.name / instance_id
    started_at = dt.datetime.now(dt.UTC).isoformat()
    wall_start = time.monotonic()
    checkout_error = ""
    timed_out = False
    timeout_stdout = ""
    timeout_stderr = ""
    run_result: subprocess.CompletedProcess[str] | None = None
    patch = ""
    status = ""
    run_id = ""
    replay = {"verified": False, "returncode": 1, "stdout": "", "stderr": "", "trace_sha256": "", "command": []}
    try:
        checkout_task_repo(task, task_dir)
        prompt = benchmark_prompt(task)
        if not prompt:
            raise RuntimeError("empty SWE-bench problem_statement")
        planner = write_planner(task_out / "planner.py", task, args.agent)
        command = poor_cli_run_command(args, store_dir, prompt)
        run_result = run_command(command, cwd=task_dir, timeout=args.timeout_seconds, env=poor_cli_env(args, planner))
        run_id = extract_run_id(run_result.stdout)
        patch = git_diff(task_dir)
        status = git_status(task_dir)
        replay = run_replay_verify(args, task_dir, store_dir, run_id)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        timeout_stdout = exc.stdout or ""
        timeout_stderr = exc.stderr or ""
        checkout_error = f"poor-cli run timed out after {args.timeout_seconds}s"
        if task_dir.exists():
            patch = git_diff(task_dir)
            status = git_status(task_dir)
    except Exception as exc:
        checkout_error = str(exc)
    finally:
        if task_dir.exists() and not args.keep_worktrees:
            shutil.rmtree(task_dir)
    stdout = run_result.stdout if run_result is not None else timeout_stdout
    stderr = run_result.stderr if run_result is not None else timeout_stderr or checkout_error
    (task_out / "stdout.txt").write_text(stdout, encoding="utf-8")
    (task_out / "stderr.txt").write_text(stderr, encoding="utf-8")
    record = {
        "instance_id": instance_id,
        "repo": task.get("repo"),
        "base_commit": task.get("base_commit"),
        "poor_cli_run_id": run_id,
        "poor_cli_store_dir": str(store_dir),
        "replay_verified": bool(replay["verified"]),
        "replay_trace_sha256": replay["trace_sha256"],
        "agent": args.agent,
        "model": args.model,
        "provider": args.provider,
        "dataset_name": args.dataset_name,
        "dataset_revision": args.dataset_revision,
        "seed": args.seed,
        "started_at": started_at,
        "finished_at": dt.datetime.now(dt.UTC).isoformat(),
        "wall_time_seconds": round(time.monotonic() - wall_start, 3),
        "exit_code": run_result.returncode if run_result is not None else 124 if timed_out else 1,
        "cost": cost_from_payload({}),
        "git_status": status,
        "patch_bytes": len(patch.encode("utf-8")),
        "stdout_path": str(task_out / "stdout.txt"),
        "stderr_path": str(task_out / "stderr.txt"),
        "replay_returncode": replay["returncode"],
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
        "agent": args.agent,
        "budget_usd": args.budget_usd,
        "seed": args.seed,
        "task_count": len(records),
        "completed_exec_count": sum(1 for record in records if int(record.get("exit_code", 1)) == 0),
        "replay_verified_count": sum(1 for record in records if record.get("replay_verified")),
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


def confirm_cost(args: argparse.Namespace, task_count: int, *, model_calls: bool = True) -> None:
    cost_scope = "model API charges and Docker evaluation costs" if model_calls else "Docker evaluation costs"
    action = "run poor-cli on" if model_calls else "evaluate predictions for"
    warning_text = (
        f"COST WARNING: this will {action} {task_count} SWE-bench Lite task(s) "
        f"with provider={args.provider} model={args.model}. This can incur {cost_scope}."
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
    predictions_path = (run_dir / "predictions.jsonl").resolve()
    instance_ids = prediction_instance_ids(predictions_path)
    command = [
        args.python,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        args.dataset_name,
        "--split",
        args.split,
        "--predictions_path",
        str(predictions_path),
        "--max_workers",
        str(args.eval_max_workers),
        "--run_id",
        run_id,
        "--report_dir",
        str((run_dir / "evaluation").resolve()),
        "--namespace",
        args.eval_namespace,
        "--force_rebuild",
        str(args.eval_force_rebuild),
        "--cache_level",
        args.eval_cache_level,
        "--clean",
        str(args.eval_clean),
    ]
    if args.eval_timeout is not None:
        command.extend(["--timeout", str(args.eval_timeout)])
    if instance_ids:
        command.extend(["--instance_ids", *instance_ids])
    started = time.monotonic()
    result = run_command(command, cwd=run_dir, env=evaluation_env(args, run_dir))
    (run_dir / "evaluation_stdout.txt").write_text(result.stdout, encoding="utf-8")
    (run_dir / "evaluation_stderr.txt").write_text(result.stderr, encoding="utf-8")
    discovered = discovered_evaluation_reports(run_dir, run_id)
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


def resolve_existing_run_dir(args: argparse.Namespace) -> Path:
    run_dir = Path(str(args.evaluate_existing_run))
    if not run_dir.exists():
        run_dir = Path(args.results_dir) / str(args.evaluate_existing_run)
    return run_dir


def count_prediction_rows(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def prediction_instance_ids(path: Path) -> list[str]:
    instance_ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        instance_id = payload.get("instance_id") if isinstance(payload, dict) else None
        if instance_id:
            instance_ids.append(str(instance_id))
    return instance_ids


def discovered_evaluation_reports(run_dir: Path, run_id: str) -> list[Path]:
    return sorted({*run_dir.rglob("results.json"), *run_dir.glob(f"*.{run_id}.json")})


def evaluation_env(args: argparse.Namespace, run_dir: Path) -> dict[str, str] | None:
    if not args.eval_isolated_docker_config:
        return None
    docker_config = Path(args.store_root).resolve().parent / "docker-config" / run_dir.name
    write_json(docker_config / "config.json", {"auths": {}})
    env = os.environ.copy()
    env["DOCKER_CONFIG"] = str(docker_config.resolve())
    return env


def evaluate_existing_run(args: argparse.Namespace) -> int:
    run_dir = resolve_existing_run_dir(args)
    predictions = run_dir / "predictions.jsonl"
    if not predictions.exists():
        raise SystemExit(f"missing predictions.jsonl: {predictions}")
    task_count = count_prediction_rows(predictions)
    if task_count == 0:
        raise SystemExit(f"empty predictions.jsonl: {predictions}")
    confirm_cost(args, task_count, model_calls=False)
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {"run_id": run_dir.name}
    if not isinstance(summary, dict):
        raise SystemExit(f"summary root must be object: {summary_path}")
    summary["official_evaluation"] = run_official_evaluation(args, run_dir, run_dir.name)
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return int(summary["official_evaluation"].get("exit_code") or 0)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    random.seed(args.seed)
    if args.evaluate_existing_run:
        return evaluate_existing_run(args)
    manifest = load_manifest(args.manifest)
    tasks = select_tasks(
        apply_manifest(load_tasks(args.dataset_name, args.split, args.dataset_revision), manifest),
        instance_ids=args.instance_id,
        task_subset_filter=args.task_subset_filter,
        limit=args.limit,
        shuffle=args.shuffle,
        seed=args.seed,
    )
    if not tasks:
        raise SystemExit("no SWE-bench tasks selected")
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
            "manifest": args.manifest,
            "seed": args.seed,
            "provider": args.provider,
            "model": args.model,
            "agent": args.agent,
            "budget_usd": args.budget_usd,
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
