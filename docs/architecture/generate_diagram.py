#!/usr/bin/env python3
"""
Architecture diagram generator for poor-cli.

Usage:
    python3 -m venv .venv && . .venv/bin/activate
    pip install diagrams pillow
    # system: graphviz must be installed (dnf/apt/brew install graphviz)
    python3 docs/architecture/generate_diagram.py

Outputs: docs/architecture/poor_cli_architecture.png
         docs/architecture/poor_cli_architecture.svg (via graph_attr)

Downloads vendor logos on first run into docs/architecture/assets/ and
caches them. Re-run overwrites the PNG but keeps the cached logos.
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config

HERE = Path(__file__).parent.resolve()
ASSETS = HERE / "assets"
OUT_STEM = HERE / "poor_cli_architecture"

# Simpleicons.org CDN — no rate limits, monochrome SVGs in brand color.
# Colour is appended as 6-hex with no leading "#". Black (000000) keeps
# the diagram legible on white; tweak per-logo below if you want accents.
SI = "https://cdn.simpleicons.org"
LOGOS: dict[str, str] = {
    "neovim.png":     f"{SI}/neovim/57A143",      # Neovim green
    "lua.png":        f"{SI}/lua/2C2D72",         # Lua navy
    "python.png":     f"{SI}/python/3776AB",      # Python blue
    # OpenAI removed from simpleicons (branding policy); use their GH avatar.
    "openai.png":     "https://avatars.githubusercontent.com/u/14957082?s=240&v=4",
    "anthropic.png":  f"{SI}/anthropic/191919",
    "google.png":     f"{SI}/googlegemini/4285F4",
    "ollama.png":     f"{SI}/ollama/000000",
    "webrtc.png":     f"{SI}/webrtc/333333",
    "git.png":        f"{SI}/git/F05032",
    "aiohttp.png":    f"{SI}/aiohttp/2C5BB4",
    "json.png":       f"{SI}/json/000000",
    "sqlite.png":     f"{SI}/sqlite/003B57",
    "gear.png":       f"{SI}/gnuprivacyguard/0093DD",  # generic "service" stand-in
    "shield.png":     f"{SI}/cloudflare/F38020",       # generic "security/perm" stand-in
    # Plugin-dep avatars (no simpleicons entry). GitHub org avatars are stable.
    "snacks.png":     "https://avatars.githubusercontent.com/u/292349?s=240&v=4",      # folke
    "trouble.png":    "https://avatars.githubusercontent.com/u/292349?s=240&v=4",      # folke
    "dap.png":        "https://avatars.githubusercontent.com/u/700359?s=240&v=4",      # mfussenegger
    "neogit.png":     "https://avatars.githubusercontent.com/u/101884448?s=240&v=4",   # NeogitOrg
}


def fetch_logos() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, url in LOGOS.items():
        out = ASSETS / name
        if out.exists() and out.stat().st_size > 0:
            continue
        print(f"  fetching {name:<16} <- {url}", file=sys.stderr)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "poor-cli-diagram/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            # Convert SVG to PNG if we got one, since diagrams/graphviz
            # handles PNG more consistently.
            if data[:5] == b"<?xml" or data[:4] == b"<svg":
                _svg_to_png(data, out)
            else:
                out.write_bytes(data)
        except Exception as exc:
            print(f"    failed: {exc}. A placeholder will be used.", file=sys.stderr)
            # write a tiny transparent PNG as placeholder so the node still renders
            out.write_bytes(_blank_png())


def _svg_to_png(svg_bytes: bytes, out: Path) -> None:
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(bytestring=svg_bytes, write_to=str(out), output_width=240)
        return
    except ImportError:
        pass
    try:
        # cairosvg missing — try Pillow + the SVG text as fallback note.
        # Pillow can't render SVG without extras; we save the bytes as
        # a .svg next to the expected path and hope graphviz accepts it.
        svg_path = out.with_suffix(".svg")
        svg_path.write_bytes(svg_bytes)
        # Create a PNG stub so diagrams doesn't choke on missing file.
        out.write_bytes(_blank_png())
        print(f"    note: saved {svg_path.name} (install cairosvg for PNG conversion)", file=sys.stderr)
    except Exception:
        out.write_bytes(_blank_png())


def _blank_png() -> bytes:
    # 1x1 transparent PNG — minimal valid payload.
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )


def build() -> None:
    try:
        from diagrams import Cluster, Diagram, Edge
        from diagrams.custom import Custom
    except ImportError:
        print(
            "ERROR: `diagrams` not installed. Run: pip install diagrams\n"
            "       System requirement: graphviz (dnf/apt/brew install graphviz)",
            file=sys.stderr,
        )
        sys.exit(1)

    def logo(name: str) -> str:
        path = ASSETS / name
        return str(path) if path.exists() else ""

    graph_attr = {
        "bgcolor": "white",
        "pad": "0.5",
        "nodesep": "0.6",
        "ranksep": "0.9",
        "fontname": "Helvetica",
        "fontsize": "14",
        "labelloc": "t",
        "label": "poor-cli — architecture",
    }
    node_attr = {"fontname": "Helvetica", "fontsize": "11"}
    edge_attr = {"fontname": "Helvetica", "fontsize": "9", "color": "#555555"}

    with Diagram(
        "poor-cli architecture",
        filename=str(OUT_STEM),
        outformat=["png"],
        show=False,
        direction="TB",
        graph_attr=graph_attr,
        node_attr=node_attr,
        edge_attr=edge_attr,
    ):
        # --------------------------------------------------------------
        # Client layer — editor + plugin
        with Cluster("Editor (Neovim)", graph_attr={"bgcolor": "white", "style": "rounded,dashed"}):
            nvim = Custom("Neovim 0.9+", logo("neovim.png"))

            with Cluster("nvim-poor-cli (Lua)", graph_attr={"bgcolor": "#f4faff", "style": "rounded"}):
                lua_runtime = Custom("Lua runtime", logo("lua.png"))
                chat_mod = Custom("chat.lua\n(chat panel,\nstreaming, tools)", logo("lua.png"))
                rpc_mod = Custom("rpc.lua\n(stdio JSON-RPC,\nstate machine)", logo("lua.png"))
                panels_mod = Custom("panels/*\n(tasks, agents,\ntimeline, diff)", logo("lua.png"))
                inline_mod = Custom("inline.lua\n(ghost-text\ncompletion)", logo("lua.png"))
                mp_mod = Custom("multiplayer_room.lua\n(collab UI)", logo("lua.png"))

            with Cluster("Required plugins", graph_attr={"bgcolor": "#fffaf2", "style": "rounded"}):
                snacks = Custom("snacks.nvim\n(notify + pickers)", logo("neovim.png"))
                trouble = Custom("trouble.nvim\n(diagnostics)", logo("neovim.png"))
                dap = Custom("nvim-dap\n(breakpoints)", logo("neovim.png"))
                neogit = Custom("neogit\n(commit flow)", logo("neovim.png"))

        # --------------------------------------------------------------
        # Transport
        stdio = Custom("stdio JSON-RPC\n(bidirectional, streaming)", logo("json.png"))

        # --------------------------------------------------------------
        # Backend — Python server
        with Cluster("poor-cli-server (Python 3.11+)", graph_attr={"bgcolor": "#f9f5ff", "style": "rounded"}):
            py_runtime = Custom("Python", logo("python.png"))

            with Cluster("core", graph_attr={"bgcolor": "white", "style": "rounded,dotted"}):
                core_loop = Custom("agent loop\n(turn lifecycle,\ntool dispatch)", logo("python.png"))
                handlers = Custom("RPC handlers\n(chat / tools /\nsession / config)", logo("python.png"))
                tool_reg = Custom("tool registry\n(53 tools: bash,\nread/write, grep…)", logo("python.png"))

            with Cluster("stateful services", graph_attr={"bgcolor": "white", "style": "rounded,dotted"}):
                session_mgr = Custom("session +\nhistory manager", logo("python.png"))
                checkpoint = Custom("checkpoint\nmanager", logo("python.png"))
                perm = Custom("permission +\naudit + sandbox", logo("shield.png"))
                cost = Custom("cost tracker\n(per-turn + daily)", logo("python.png"))
                file_cache = Custom("file cache +\nindexer", logo("python.png"))

            with Cluster("multiplayer", graph_attr={"bgcolor": "white", "style": "rounded,dotted"}):
                mp_host = Custom("signaling host\n(aiohttp /rpc)", logo("aiohttp.png"))
                mp_bridge = Custom("P2P bridge\n(aiortc)", logo("webrtc.png"))
                mp_session = Custom("session layer\n(roles, queue,\nagenda)", logo("python.png"))

        # --------------------------------------------------------------
        # External providers
        with Cluster("LLM providers", graph_attr={"bgcolor": "#fff7f7", "style": "rounded"}):
            openai = Custom("OpenAI\n(gpt-5.1,\no-series reasoning)", logo("openai.png"))
            anthropic = Custom("Anthropic\n(claude-sonnet-4,\nextended thinking)", logo("anthropic.png"))
            gemini = Custom("Gemini\n(2.5 flash / pro)", logo("google.png"))
            ollama = Custom("Ollama\n(local inference)", logo("ollama.png"))

        # --------------------------------------------------------------
        # Repo + local state
        with Cluster("local state", graph_attr={"bgcolor": "#f7fbf7", "style": "rounded"}):
            repo = Custom("repo\n(.poor-cli/ per-repo\nconfig + checkpoints)", logo("git.png"))
            keyring = Custom("OS keyring\n(provider API keys)", logo("shield.png"))
            repo_index = Custom("repo index\n(PageRank,\nsymbols, edges)", logo("sqlite.png"))

        # --------------------------------------------------------------
        # Remote peer (other laptop)
        remote_peer = Custom("Remote participant\n(another Neovim +\nbridge subprocess)", logo("neovim.png"))

        # --------------------------------------------------------------
        # Edges — client layer internals
        nvim >> Edge(style="invis") >> lua_runtime
        chat_mod - Edge(style="invis") - rpc_mod
        chat_mod >> Edge(color="#0088cc", label="notify /\npicker") >> snacks
        panels_mod >> Edge(style="dashed", color="#aa6600", label="optional") >> trouble
        chat_mod >> Edge(style="dashed", color="#aa6600", label="breakpoints") >> dap
        chat_mod >> Edge(style="dashed", color="#aa6600", label="commits") >> neogit

        # client → transport → backend
        rpc_mod >> Edge(color="#222222", label="spawn +\nJSON-RPC", penwidth="2") >> stdio
        stdio >> Edge(color="#222222") >> handlers

        # backend internal wiring
        handlers >> core_loop
        core_loop >> tool_reg
        core_loop >> session_mgr
        core_loop >> checkpoint
        core_loop >> perm
        core_loop >> cost
        tool_reg >> file_cache

        # backend → providers
        core_loop >> Edge(color="#cc3333", label="chat /\ncompletion") >> openai
        core_loop >> Edge(color="#cc3333") >> anthropic
        core_loop >> Edge(color="#cc3333") >> gemini
        core_loop >> Edge(color="#cc3333", style="dashed", label="local") >> ollama

        # backend ↔ local state
        session_mgr >> Edge(color="#228844") >> repo
        checkpoint >> Edge(color="#228844") >> repo
        perm >> Edge(color="#228844", label="audit.db") >> repo
        file_cache >> Edge(color="#228844", style="dashed") >> repo_index
        handlers >> Edge(color="#228844", style="dashed", label="credentials") >> keyring

        # multiplayer wiring
        mp_mod >> Edge(color="#aa33aa", label="join /\nhost ctrl") >> handlers
        handlers >> mp_session
        mp_session >> mp_host
        mp_session >> mp_bridge
        mp_bridge >> Edge(color="#aa33aa", label="WebRTC\nDataChannel", penwidth="2") >> remote_peer

    print(f"\n✓ wrote {OUT_STEM.with_suffix('.png')}")


if __name__ == "__main__":
    print("Fetching logos...", file=sys.stderr)
    fetch_logos()
    print("Building diagram...", file=sys.stderr)
    build()
