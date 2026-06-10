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
    category: str = "General"
    icon: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "promptScaffold": self.prompt_scaffold,
            "sandboxPreset": self.sandbox_preset,
            "contextStrategy": self.context_strategy,
            "followUpCommands": list(self.follow_up_commands),
            "category": self.category,
            "icon": self.icon,
        }


_BUILTIN_WORKFLOWS: Dict[str, WorkflowTemplate] = {
    # ── General ──────────────────────────────────────────────────────
    "review": WorkflowTemplate(
        name="review",
        title="Review A Change",
        description="Inspect a diff or feature area for bugs, regressions, and missing tests.",
        prompt_scaffold="Review the current changes with a code-review mindset. Prioritize bugs, behavioral regressions, risky assumptions, and missing tests. Cite the affected files and explain the user impact.",
        sandbox_preset="review-only",
        context_strategy="git-changed-first",
        follow_up_commands=["/status", "/context explain", "/checkpoints", "/review"],
        category="General",
        icon="🔍",
    ),
    "debug": WorkflowTemplate(
        name="debug",
        title="Debug A Failure",
        description="Diagnose a failing command, broken feature, or unexpected runtime behavior.",
        prompt_scaffold="Debug the reported issue. Start by reproducing or inspecting the failure, identify the most likely root cause, and propose or implement the smallest correct fix.",
        sandbox_preset="review-only",
        context_strategy="error-first",
        follow_up_commands=["/doctor", "/context explain", "/task create", "/qa status"],
        category="General",
        icon="🐛",
    ),
    "implement": WorkflowTemplate(
        name="implement",
        title="Implement A Change",
        description="Make a scoped product or code change with context and rollback awareness.",
        prompt_scaffold="Implement the requested change end-to-end. Prefer the smallest coherent change that satisfies the request, update related tests, and summarize what changed and why.",
        sandbox_preset="workspace-write",
        context_strategy="backend-owned",
        follow_up_commands=["/trust", "/context explain", "/checkpoint", "/task create"],
        category="General",
        icon="🔧",
    ),
    "summarize": WorkflowTemplate(
        name="summarize",
        title="Summarize A Repo Or Area",
        description="Explain the relevant architecture, behavior, and current state clearly.",
        prompt_scaffold="Summarize the relevant codebase area. Focus on architecture, key behavior, risks, and the parts a new engineer should understand first.",
        sandbox_preset="read-only",
        context_strategy="overview-first",
        follow_up_commands=["/status", "/context explain", "/history 10", "/runs"],
        category="General",
        icon="📋",
    ),
    "qa": WorkflowTemplate(
        name="qa",
        title="Run A QA Loop",
        description="Check the repo health, identify obvious breakage, and suggest next actions.",
        prompt_scaffold="Run a QA-oriented pass over the current workspace. Identify failing checks, likely user-visible regressions, and the best next verification steps.",
        sandbox_preset="review-only",
        context_strategy="repo-health",
        follow_up_commands=["/doctor", "/qa status", "/task create", "/automation list"],
        category="General",
        icon="✅",
    ),

    # ── Status Reports ───────────────────────────────────────────────
    "standup": WorkflowTemplate(
        name="standup",
        title="Daily Standup Summary",
        description="Summarize yesterday's git activity for standup.",
        prompt_scaffold="Summarize git activity from the last 24 hours. List commits by author, highlight key changes, flag anything that looks risky or incomplete. Format as a standup update.",
        sandbox_preset="read-only",
        context_strategy="git-recent",
        follow_up_commands=["/status", "/cost"],
        category="Status Reports",
        icon="💬",
    ),
    "weekly-update": WorkflowTemplate(
        name="weekly-update",
        title="Weekly Update",
        description="Synthesize this week's PRs, rollouts, incidents, and reviews into a weekly update.",
        prompt_scaffold="Synthesize the past week of activity: merged PRs, open PRs, any incidents or reverts, review comments, and deployment activity. Produce a concise weekly status report.",
        sandbox_preset="read-only",
        context_strategy="git-weekly",
        follow_up_commands=["/status", "/runs"],
        category="Status Reports",
        icon="📊",
    ),
    "pr-summary": WorkflowTemplate(
        name="pr-summary",
        title="PR Summary By Team",
        description="Summarize last week's PRs by teammate and theme; highlight risks.",
        prompt_scaffold="List all PRs merged or opened in the last 7 days. Group by author, identify themes (features, fixes, refactors), and flag any that look risky or need follow-up.",
        sandbox_preset="read-only",
        context_strategy="git-weekly",
        follow_up_commands=["/status"],
        category="Status Reports",
        icon="👥",
    ),

    # ── Release Prep ─────────────────────────────────────────────────
    "release-notes": WorkflowTemplate(
        name="release-notes",
        title="Draft Release Notes",
        description="Draft weekly release notes from merged PRs (include links when available).",
        prompt_scaffold="Draft release notes from recently merged PRs. Group by category (features, fixes, improvements). Include PR numbers/links where available. Write for end-users, not developers.",
        sandbox_preset="read-only",
        context_strategy="git-recent",
        follow_up_commands=["/status", "/export"],
        category="Release Prep",
        icon="📖",
    ),
    "release-check": WorkflowTemplate(
        name="release-check",
        title="Pre-Release Verification",
        description="Before tagging, verify changelog, migrations, feature flags, and tests.",
        prompt_scaffold="Run a pre-release verification: check that CHANGELOG is updated, all migrations are reversible, feature flags are documented, tests pass, and no TODO/FIXME markers remain in changed files.",
        sandbox_preset="review-only",
        context_strategy="repo-health",
        follow_up_commands=["/doctor", "/qa status", "/checkpoints"],
        category="Release Prep",
        icon="✅",
    ),
    "changelog": WorkflowTemplate(
        name="changelog",
        title="Update Changelog",
        description="Update the changelog with this week's highlights and key PR links.",
        prompt_scaffold="Update CHANGELOG.md with this week's changes. Group entries by: Added, Changed, Fixed, Removed. Include PR numbers. Follow Keep a Changelog format.",
        sandbox_preset="workspace-write",
        context_strategy="git-recent",
        follow_up_commands=["/checkpoint", "/diff"],
        category="Release Prep",
        icon="📝",
    ),

    # ── Incidents & Triage ───────────────────────────────────────────
    "ci-failures": WorkflowTemplate(
        name="ci-failures",
        title="Summarize CI Failures",
        description="Summarize CI failures and flaky tests from the last CI window; suggest top fixes.",
        prompt_scaffold="Analyze recent CI failures and test results. Identify flaky tests vs real failures, group by root cause, and suggest the highest-leverage fixes to unblock the pipeline.",
        sandbox_preset="review-only",
        context_strategy="error-first",
        follow_up_commands=["/doctor", "/fix-failures", "/task create"],
        category="Incidents & Triage",
        icon="🔄",
    ),
    "ci-debug": WorkflowTemplate(
        name="ci-debug",
        title="Debug CI Failure",
        description="Check CI failures; group by likely root cause and suggest minimal fixes.",
        prompt_scaffold="Debug the latest CI failure. Read the error output, identify the root cause, check if it's a flaky test or real regression, and propose the smallest fix.",
        sandbox_preset="review-only",
        context_strategy="error-first",
        follow_up_commands=["/fix-failures", "/debug"],
        category="Incidents & Triage",
        icon="💻",
    ),
    "triage": WorkflowTemplate(
        name="triage",
        title="Triage Issues",
        description="Triage new issues; suggest owner, priority, and labels.",
        prompt_scaffold="Review open issues/bugs. For each, suggest: priority (P0-P3), likely owner based on code ownership, appropriate labels, and whether it's a duplicate of an existing issue.",
        sandbox_preset="read-only",
        context_strategy="overview-first",
        follow_up_commands=["/status"],
        category="Incidents & Triage",
        icon="⚠️",
    ),

    # ── Code Quality ─────────────────────────────────────────────────
    "scan-bugs": WorkflowTemplate(
        name="scan-bugs",
        title="Scan For Bugs",
        description="Scan recent commits (since last run, or last 24h) for likely bugs and propose minimal fixes.",
        prompt_scaffold="Scan commits from the last 24 hours for potential bugs: null dereferences, race conditions, missing error handling, SQL injection, XSS, or logic errors. For each finding, cite the file and line, explain the risk, and propose a minimal fix.",
        sandbox_preset="review-only",
        context_strategy="git-recent",
        follow_up_commands=["/review", "/fix-failures"],
        category="Code Quality",
        icon="🐞",
    ),
    "test-coverage": WorkflowTemplate(
        name="test-coverage",
        title="Improve Test Coverage",
        description="Identify untested paths from recent changes; add focused tests.",
        prompt_scaffold="Identify code paths in recently changed files that lack test coverage. Generate focused unit tests for the most critical untested paths. Prioritize error handling and edge cases.",
        sandbox_preset="workspace-write",
        context_strategy="git-changed-first",
        follow_up_commands=["/test", "/checkpoint"],
        category="Code Quality",
        icon="🧪",
    ),
    "perf-audit": WorkflowTemplate(
        name="perf-audit",
        title="Performance Audit",
        description="Compare recent changes to benchmarks or traces and flag regressions early.",
        prompt_scaffold="Audit recent changes for performance impact: N+1 queries, unnecessary allocations, blocking I/O on hot paths, missing caching, oversized payloads. Flag regressions and suggest fixes.",
        sandbox_preset="review-only",
        context_strategy="git-changed-first",
        follow_up_commands=["/review"],
        category="Code Quality",
        icon="📈",
    ),

    # ── Repo Maintenance ─────────────────────────────────────────────
    "dep-drift": WorkflowTemplate(
        name="dep-drift",
        title="Dependency Drift Check",
        description="Detect dependency and SDK drift and propose a minimal alignment plan.",
        prompt_scaffold="Check for dependency drift: outdated packages, security advisories, version conflicts between sub-projects, and deprecated APIs. Propose a minimal, safe upgrade plan.",
        sandbox_preset="review-only",
        context_strategy="repo-health",
        follow_up_commands=["/doctor"],
        category="Repo Maintenance",
        icon="✅",
    ),
    "dep-upgrade": WorkflowTemplate(
        name="dep-upgrade",
        title="Upgrade Dependencies",
        description="Scan outdated dependencies; propose safe upgrades with minimal changes.",
        prompt_scaffold="Scan for outdated dependencies. For each, check if the upgrade is safe (breaking changes, migration guide). Propose a batch of safe upgrades and generate the update commands.",
        sandbox_preset="workspace-write",
        context_strategy="repo-health",
        follow_up_commands=["/checkpoint", "/test"],
        category="Repo Maintenance",
        icon="📦",
    ),
    "update-docs": WorkflowTemplate(
        name="update-docs",
        title="Update Project Docs",
        description="Update AGENTS.md with newly discovered workflows and commands.",
        prompt_scaffold="Review the current AGENTS.md/README and update it with any new workflows, commands, or patterns discovered in recent changes. Keep it concise and developer-focused.",
        sandbox_preset="workspace-write",
        context_strategy="overview-first",
        follow_up_commands=["/checkpoint"],
        category="Repo Maintenance",
        icon="📄",
    ),

    # ── Growth & Exploration ─────────────────────────────────────────
    "skill-suggest": WorkflowTemplate(
        name="skill-suggest",
        title="Suggest Next Skills",
        description="From recent PRs and reviews, suggest next skills to deepen.",
        prompt_scaffold="Analyze recent PRs, review comments, and code patterns. Identify areas where the team could improve: missing patterns, repeated mistakes, or technologies worth learning. Suggest concrete next steps.",
        sandbox_preset="read-only",
        context_strategy="overview-first",
        follow_up_commands=["/status"],
        category="Growth & Exploration",
        icon="🗂️",
    ),
    "perf-opportunity": WorkflowTemplate(
        name="perf-opportunity",
        title="Find Performance Opportunities",
        description="Audit performance regressions and propose highest-leverage fixes.",
        prompt_scaffold="Identify the top 5 performance improvement opportunities in this codebase. Consider: database queries, API response times, bundle sizes, memory usage, and startup time. Rank by expected impact.",
        sandbox_preset="read-only",
        context_strategy="overview-first",
        follow_up_commands=["/review"],
        category="Growth & Exploration",
        icon="🚀",
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
