"""
Deterministic per-turn context contract blocks.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .instructions import InstructionManager, InstructionSnapshot


@dataclass(frozen=True)
class ContextContractSnapshot:
    system_context: str
    user_context: str
    rendered_prompt_prefix: str

    def to_dict(self) -> dict:
        return {
            "systemContext": self.system_context,
            "userContext": self.user_context,
            "renderedPromptPrefix": self.rendered_prompt_prefix,
        }


class ContextContractManager:
    """Builds memoized system/user context blocks for each model turn."""

    def __init__(
        self,
        repo_root: Path,
        instruction_manager: Optional[InstructionManager] = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self._instruction_manager = instruction_manager or InstructionManager(self.repo_root)
        self._system_cache_key: str = ""
        self._system_cache_value: str = ""
        self._user_cache_key: str = ""
        self._user_cache_value: str = ""

    def invalidate_cache(self) -> None:
        self._system_cache_key = ""
        self._system_cache_value = ""
        self._user_cache_key = ""
        self._user_cache_value = ""

    def build_snapshot(
        self,
        *,
        referenced_files: Optional[Sequence[str]] = None,
        plan_mode_enabled: bool = False,
        repo_summary: str = "",
        instruction_snapshot: Optional[InstructionSnapshot] = None,
    ) -> ContextContractSnapshot:
        resolved_snapshot = instruction_snapshot or self._instruction_manager.build_snapshot(
            list(referenced_files or []),
            plan_mode_enabled=plan_mode_enabled,
            repo_summary=repo_summary,
        )

        system_context = self._build_system_context()
        user_context = self._build_user_context(
            instruction_snapshot=resolved_snapshot,
            referenced_files=referenced_files or [],
            plan_mode_enabled=plan_mode_enabled,
            repo_summary=repo_summary,
        )
        rendered = (
            "## System Context\n"
            f"{system_context}\n\n"
            "## User Context\n"
            f"{user_context}"
        )
        return ContextContractSnapshot(
            system_context=system_context,
            user_context=user_context,
            rendered_prompt_prefix=rendered,
        )

    def _build_system_context(self) -> str:
        branch = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        default_branch = self._resolve_default_branch()
        git_user = self._run_git("config", "user.name")
        status_short = self._run_git("status", "--short")
        status_short = status_short[:2000] if status_short else ""
        git_log = self._run_git("log", "--oneline", "-5")

        key = hashlib.sha256(
            "|".join(
                [
                    str(self.repo_root),
                    branch,
                    default_branch,
                    git_user,
                    status_short,
                    git_log,
                ]
            ).encode("utf-8", errors="replace")
        ).hexdigest()
        if key == self._system_cache_key and self._system_cache_value:
            return self._system_cache_value

        lines = [f"CWD: {self.repo_root}"]
        if branch:
            lines.append(f"Current branch: {branch}")
        if default_branch:
            lines.append(f"Default branch: {default_branch}")
        if git_user:
            lines.append(f"Git user: {git_user}")
        if status_short:
            lines.append("git status --short:")
            lines.append(status_short)
        if git_log:
            lines.append("Recent commits (git log --oneline -5):")
            lines.append(git_log)
        if len(lines) == 1:
            lines.append("Git context unavailable for current working directory.")

        rendered = "\n".join(lines).strip()
        self._system_cache_key = key
        self._system_cache_value = rendered
        return rendered

    def _build_user_context(
        self,
        *,
        instruction_snapshot: InstructionSnapshot,
        referenced_files: Sequence[str],
        plan_mode_enabled: bool,
        repo_summary: str,
    ) -> str:
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        referenced = sorted(str(path) for path in referenced_files if str(path).strip())
        rendered_stack = instruction_snapshot.render_prompt_prefix().strip()
        stack_hash = hashlib.sha256(rendered_stack.encode("utf-8", errors="replace")).hexdigest()
        repo_summary_hash = hashlib.sha256(repo_summary.encode("utf-8", errors="replace")).hexdigest()[:16] if repo_summary else ""

        key = hashlib.sha256(
            "|".join(
                [
                    str(self.repo_root),
                    current_date,
                    str(plan_mode_enabled),
                    repo_summary_hash,
                    stack_hash,
                    ",".join(referenced),
                ]
            ).encode("utf-8", errors="replace")
        ).hexdigest()
        if key == self._user_cache_key and self._user_cache_value:
            return self._user_cache_value

        lines = [f"Today's date is {current_date}."]
        if referenced:
            lines.append("Referenced files:")
            lines.extend(f"- {path}" for path in referenced[:50])
        lines.append("Resolved instruction stack:")
        if rendered_stack:
            lines.append(rendered_stack)
        else:
            lines.append("(none)")

        rendered = "\n".join(lines).strip()
        self._user_cache_key = key
        self._user_cache_value = rendered
        return rendered

    def _resolve_default_branch(self) -> str:
        remote_head = self._run_git("symbolic-ref", "refs/remotes/origin/HEAD")
        if remote_head.startswith("refs/remotes/origin/"):
            return remote_head.split("/")[-1]

        for candidate in ("main", "master"):
            probe = self._run_git("rev-parse", "--verify", candidate)
            if probe:
                return candidate
        return ""

    def _run_git(self, *args: str) -> str:
        try:
            output = subprocess.check_output(
                ["git", *args],
                cwd=self.repo_root,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            )
        except Exception:
            return ""
        return output.strip()
