#!/usr/bin/env python3
"""Generate architecture diagram for poor-cli using the diagrams library."""

import os
from diagrams import Diagram, Cluster, Edge
from diagrams.programming.language import Python, Rust, Bash
from diagrams.custom import Custom
from diagrams.onprem.client import User, Users
from diagrams.onprem.container import Docker
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.vcs import Github
from diagrams.onprem.database import PostgreSQL
from diagrams.generic.storage import Storage
from diagrams.generic.network import Firewall
from diagrams.generic.device import Tablet

ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons")

def icon(name):
    return os.path.join(ICONS_DIR, name)

graph_attr = {
    "bgcolor": "white",
    "fontsize": "28",
    "fontname": "Helvetica Bold",
    "pad": "0.8",
    "nodesep": "0.8",
    "ranksep": "1.2",
    "splines": "spline",
    "dpi": "200",
}

node_attr = {
    "fontsize": "11",
    "fontname": "Helvetica",
}

edge_attr = {
    "fontsize": "9",
    "fontname": "Helvetica",
    "color": "#555555",
}

cluster_attr = {
    "fontsize": "14",
    "fontname": "Helvetica Bold",
    "style": "rounded",
    "bgcolor": "#f8f9fa",
    "pencolor": "#dee2e6",
}

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "architecture")

with Diagram(
    "poor-cli Architecture",
    filename=OUTPUT_PATH,
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
    outformat="png",
):

    # --- Users / Entry Points ---
    user = User("Developer")

    with Cluster("Editor Integrations", graph_attr={**cluster_attr, "bgcolor": "#fff3e0"}):
        neovim = Custom("Neovim\nPlugin (Lua)", icon("neovim.png"))
        emacs = Tablet("Emacs\nPlugin (Elisp)")

    with Cluster("CLI Entry Points", graph_attr={**cluster_attr, "bgcolor": "#e3f2fd"}):
        tui = Rust("Terminal UI\n(Ratatui)")
        cli_headless = Python("Headless CLI\n(__main__.py)")

    # --- Core Server ---
    with Cluster("Core Engine (Python 3.11+)", graph_attr={**cluster_attr, "bgcolor": "#e8f5e9"}):

        server = Python("JSON-RPC Server\n(runtime.py)")

        with Cluster("Agentic Core", graph_attr={**cluster_attr, "bgcolor": "#c8e6c9"}):
            core_engine = Python("Core Engine\n(core.py)")
            tools = Python("Async Tools\n(tools_async.py)")
            planner = Python("Planner\n(plan_*.py)")
            context_mgr = Python("Context Manager\n(context.py)")

        with Cluster("Task & Automation", graph_attr={**cluster_attr, "bgcolor": "#c8e6c9"}):
            task_mgr = Python("Task Manager\n(task_manager.py)")
            automation = Python("Automation\n(automation_manager.py)")
            checkpoint = Storage("Checkpoints\n(checkpoint.py)")

        with Cluster("Security & Policy", graph_attr={**cluster_attr, "bgcolor": "#c8e6c9"}):
            sandbox = Firewall("Sandbox\n(sandbox.py)")
            policy = Python("Policy Hooks\n(policy_hooks.py)")
            audit = Python("Audit Log\n(audit_log.py)")

        with Cluster("Collaboration", graph_attr={**cluster_attr, "bgcolor": "#c8e6c9"}):
            multiplayer = Users("Multiplayer\n(WebRTC / aiortc)")
            mcp = Python("MCP Client\n(mcp_client.py)")

        economy = Python("Economy\n(economy.py)")
        repo_graph = Python("Repo Analysis\n(repo_graph.py)")

    # --- AI Providers ---
    with Cluster("AI Model Providers", graph_attr={**cluster_attr, "bgcolor": "#fce4ec"}):
        provider_base = Python("Provider\nAbstraction\n(base.py)")
        gemini = Custom("Google Gemini\n(default)", icon("gemini.png"))
        openai_node = Custom("OpenAI\nGPT-5.x", icon("openai.png"))
        anthropic_node = Custom("Anthropic\nClaude", icon("anthropic.png"))
        ollama_node = Custom("Ollama\n(Local)", icon("ollama.png"))

    # --- Infrastructure ---
    with Cluster("Infrastructure & CI/CD", graph_attr={**cluster_attr, "bgcolor": "#f3e5f5"}):
        docker = Docker("Docker\n(Multi-stage)")
        ghcr = Docker("GHCR\nContainer Registry")
        pypi = Python("PyPI\nPackage")
        gh_actions = GithubActions("GitHub Actions\nCI/CD")
        gh_releases = Github("GitHub\nReleases")

    # --- Local Storage ---
    with Cluster("Local Storage (~/.poor-cli/)", graph_attr={**cluster_attr, "bgcolor": "#fff8e1"}):
        sqlite = PostgreSQL("SQLite\n(Tasks/State)")
        json_store = Storage("JSON Config\n& History")
        worktrees = Storage("Git Worktrees")

    # --- Optional Services ---
    with Cluster("External Services", graph_attr={**cluster_attr, "bgcolor": "#e0f7fa"}):
        brave = Bash("Brave Search\nAPI")
        web_search = Python("Web Search\n(web_search.py)")

    # --- Connections ---

    # User to entry points
    user >> Edge(color="#1565c0", style="bold") >> tui
    user >> Edge(color="#1565c0", style="bold") >> cli_headless
    user >> Edge(color="#e65100", style="bold") >> neovim
    user >> Edge(color="#e65100", style="bold") >> emacs

    # Entry points to server
    tui >> Edge(label="JSON-RPC", color="#2e7d32") >> server
    cli_headless >> Edge(color="#2e7d32") >> server
    neovim >> Edge(label="JSON-RPC", color="#e65100") >> server
    emacs >> Edge(label="JSON-RPC", color="#e65100") >> server

    # Server to core
    server >> Edge(color="#2e7d32") >> core_engine
    core_engine >> Edge(color="#388e3c") >> tools
    core_engine >> Edge(color="#388e3c") >> planner
    core_engine >> Edge(color="#388e3c") >> context_mgr

    # Core to providers
    core_engine >> Edge(label="multi-provider", color="#c62828", style="bold") >> provider_base
    provider_base >> Edge(color="#c62828") >> gemini
    provider_base >> Edge(color="#c62828") >> openai_node
    provider_base >> Edge(color="#c62828") >> anthropic_node
    provider_base >> Edge(color="#c62828") >> ollama_node

    # Core to task/automation
    core_engine >> Edge(color="#388e3c") >> task_mgr
    core_engine >> Edge(color="#388e3c") >> automation
    task_mgr >> Edge(color="#6a1b9a") >> checkpoint
    task_mgr >> Edge(color="#6a1b9a") >> worktrees

    # Core to security
    core_engine >> Edge(color="#f57f17") >> sandbox
    sandbox >> Edge(color="#f57f17") >> policy
    policy >> Edge(color="#f57f17") >> audit

    # Core to collaboration
    core_engine >> Edge(color="#00838f") >> multiplayer
    core_engine >> Edge(color="#00838f") >> mcp

    # Core to economy & repo
    core_engine >> Edge(color="#388e3c") >> economy
    core_engine >> Edge(color="#388e3c") >> repo_graph

    # Storage connections
    task_mgr >> Edge(color="#f9a825") >> sqlite
    core_engine >> Edge(color="#f9a825") >> json_store

    # Web search
    core_engine >> Edge(color="#00838f") >> web_search
    web_search >> Edge(color="#00838f") >> brave

    # CI/CD connections
    gh_actions >> Edge(color="#6a1b9a") >> docker
    gh_actions >> Edge(color="#6a1b9a") >> gh_releases
    gh_actions >> Edge(color="#6a1b9a") >> pypi
    docker >> Edge(color="#6a1b9a") >> ghcr

print(f"Architecture diagram saved to {OUTPUT_PATH}.png")
