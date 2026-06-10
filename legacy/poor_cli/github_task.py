"""Build durable tasks from GitHub PR or issue event context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .task_manager import TaskManager, TaskRecord


@dataclass(frozen=True)
class GitHubTaskContext:
    kind: str
    event_name: str
    repository: str
    number: int
    title: str
    body: str
    url: str
    author: str
    base_ref: str = ""
    head_ref: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "eventName": self.event_name,
            "repository": self.repository,
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "author": self.author,
            "baseRef": self.base_ref,
            "headRef": self.head_ref,
        }


def load_github_context(
    event_path: Optional[Path] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> GitHubTaskContext:
    env_map = dict(env or {})
    path = event_path
    if path is None:
        raw_path = str(env_map.get("GITHUB_EVENT_PATH", "")).strip()
        if raw_path:
            path = Path(raw_path).expanduser()
    if path is None or not path.exists() or path.is_dir():
        raise FileNotFoundError("GitHub event payload not found. Pass --event-path or set GITHUB_EVENT_PATH.")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub event payload must be a JSON object.")

    event_name = str(env_map.get("GITHUB_EVENT_NAME") or payload.get("action") or "github").strip()
    repository = (
        str(payload.get("repository", {}).get("full_name", "")).strip()
        or str(env_map.get("GITHUB_REPOSITORY", "")).strip()
    )

    if isinstance(payload.get("pull_request"), dict):
        pr = payload["pull_request"]
        return GitHubTaskContext(
            kind="pull_request",
            event_name=event_name,
            repository=repository,
            number=int(pr.get("number") or payload.get("number") or 0),
            title=str(pr.get("title", "")).strip(),
            body=str(pr.get("body", "") or "").strip(),
            url=str(pr.get("html_url", "")).strip(),
            author=str(pr.get("user", {}).get("login", "")).strip(),
            base_ref=str(pr.get("base", {}).get("ref", "")).strip(),
            head_ref=str(pr.get("head", {}).get("ref", "")).strip(),
        )

    if isinstance(payload.get("issue"), dict):
        issue = payload["issue"]
        return GitHubTaskContext(
            kind="issue",
            event_name=event_name,
            repository=repository,
            number=int(issue.get("number") or payload.get("number") or 0),
            title=str(issue.get("title", "")).strip(),
            body=str(issue.get("body", "") or "").strip(),
            url=str(issue.get("html_url", "")).strip(),
            author=str(issue.get("user", {}).get("login", "")).strip(),
        )

    raise ValueError("GitHub payload does not contain a pull_request or issue object.")


def default_mode_for_context(context: GitHubTaskContext) -> str:
    return "review-only" if context.kind == "pull_request" else "read-only"


def build_task_prompt(context: GitHubTaskContext, *, mode: str) -> str:
    intro = (
        "Review the pull request against the checked-out repository. "
        "Inspect the code, summarize findings, and do not modify files."
        if context.kind == "pull_request"
        else "Analyze the issue against the checked-out repository. "
        "Summarize relevant code areas, risks, and next safe implementation steps without modifying files."
    )
    if mode == "review-only":
        intro = (
            "Stay in review mode. Inspect code and behavior, report findings, and do not modify files."
        )

    lines = [
        intro,
        "",
        "GitHub context:",
        f"- Event: {context.event_name}",
        f"- Repository: {context.repository or 'unknown'}",
        f"- Kind: {context.kind}",
        f"- Number: #{context.number}",
        f"- Title: {context.title or '(untitled)'}",
        f"- Author: {context.author or 'unknown'}",
        f"- URL: {context.url or 'unknown'}",
    ]
    if context.base_ref or context.head_ref:
        lines.append(f"- Base ref: {context.base_ref or 'unknown'}")
        lines.append(f"- Head ref: {context.head_ref or 'unknown'}")
    if context.body:
        lines.extend(["", "Body:", context.body])
    return "\n".join(lines).strip()


def build_task_title(context: GitHubTaskContext) -> str:
    prefix = "PR" if context.kind == "pull_request" else "Issue"
    title = context.title or "(untitled)"
    return f"{prefix} #{context.number}: {title}"[:80]


def create_task_from_context(
    manager: TaskManager,
    context: GitHubTaskContext,
    *,
    mode: Optional[str] = None,
    auto_start: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> TaskRecord:
    sandbox_preset = str(mode or default_mode_for_context(context)).strip() or default_mode_for_context(context)
    prompt = build_task_prompt(context, mode=sandbox_preset)
    metadata_payload = context.to_dict()
    if isinstance(metadata, dict):
        metadata_payload.update(metadata)
    return manager.create_task(
        title=build_task_title(context),
        prompt=prompt,
        sandbox_preset=sandbox_preset,
        source="github",
        metadata=metadata_payload,
        auto_start=auto_start,
        requires_approval=False,
    )
