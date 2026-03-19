"""Built-in workflow templates for guided onboarding and execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class WorkflowTemplate:
    name: str
    title: str
    description: str
    prompt_scaffold: str
    sandbox_preset: str
    context_strategy: str
    follow_up_commands: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "promptScaffold": self.prompt_scaffold,
            "sandboxPreset": self.sandbox_preset,
            "contextStrategy": self.context_strategy,
            "followUpCommands": list(self.follow_up_commands),
        }


_BUILTIN_WORKFLOWS: Dict[str, WorkflowTemplate] = {
    "review": WorkflowTemplate(
        name="review",
        title="Review A Change",
        description="Inspect a diff or feature area for bugs, regressions, and missing tests.",
        prompt_scaffold=(
            "Review the current changes with a code-review mindset. Prioritize bugs, "
            "behavioral regressions, risky assumptions, and missing tests. Cite the affected "
            "files and explain the user impact."
        ),
        sandbox_preset="review-only",
        context_strategy="git-changed-first",
        follow_up_commands=["/status", "/context explain", "/checkpoints", "/review"],
    ),
    "debug": WorkflowTemplate(
        name="debug",
        title="Debug A Failure",
        description="Diagnose a failing command, broken feature, or unexpected runtime behavior.",
        prompt_scaffold=(
            "Debug the reported issue. Start by reproducing or inspecting the failure, identify "
            "the most likely root cause, and propose or implement the smallest correct fix."
        ),
        sandbox_preset="review-only",
        context_strategy="error-first",
        follow_up_commands=["/doctor", "/context explain", "/task create", "/qa status"],
    ),
    "implement": WorkflowTemplate(
        name="implement",
        title="Implement A Change",
        description="Make a scoped product or code change with context and rollback awareness.",
        prompt_scaffold=(
            "Implement the requested change end-to-end. Prefer the smallest coherent change that "
            "satisfies the request, update related tests, and summarize what changed and why."
        ),
        sandbox_preset="workspace-write",
        context_strategy="backend-owned",
        follow_up_commands=["/trust", "/context explain", "/checkpoint", "/task create"],
    ),
    "summarize": WorkflowTemplate(
        name="summarize",
        title="Summarize A Repo Or Area",
        description="Explain the relevant architecture, behavior, and current state clearly.",
        prompt_scaffold=(
            "Summarize the relevant codebase area. Focus on architecture, key behavior, risks, "
            "and the parts a new engineer should understand first."
        ),
        sandbox_preset="read-only",
        context_strategy="overview-first",
        follow_up_commands=["/status", "/context explain", "/history 10", "/runs"],
    ),
    "qa": WorkflowTemplate(
        name="qa",
        title="Run A QA Loop",
        description="Check the repo health, identify obvious breakage, and suggest next actions.",
        prompt_scaffold=(
            "Run a QA-oriented pass over the current workspace. Identify failing checks, likely "
            "user-visible regressions, and the best next verification steps."
        ),
        sandbox_preset="review-only",
        context_strategy="repo-health",
        follow_up_commands=["/doctor", "/qa status", "/task create", "/automation list"],
    ),
}


def list_workflow_templates() -> List[Dict[str, Any]]:
    return [template.to_dict() for template in _BUILTIN_WORKFLOWS.values()]


def get_workflow_template(name: str) -> Optional[Dict[str, Any]]:
    template = _BUILTIN_WORKFLOWS.get(str(name or "").strip().lower())
    if template is None:
        return None
    return template.to_dict()


def workflow_names() -> List[str]:
    return list(_BUILTIN_WORKFLOWS.keys())

