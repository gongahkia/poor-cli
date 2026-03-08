"""Generate the haus architecture diagram using the diagrams-as-code library."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from diagrams import Diagram, Cluster, Edge
from diagrams.custom import Custom
from diagrams.programming.language import Python, Javascript
from diagrams.programming.framework import Starlette
from diagrams.onprem.client import Users
from diagrams.generic.storage import Storage

ICO = "/tmp/haus_icons"

graph_attr = {
    "bgcolor": "white", "pad": "0.5", "fontsize": "20",
    "fontname": "Helvetica", "fontcolor": "#1a1a1a",
    "rankdir": "TB", "ranksep": "0.9", "nodesep": "0.6",
    "splines": "curved", "dpi": "150", "newrank": "true",
}
node_attr = {"fontsize": "11", "fontname": "Helvetica", "fontcolor": "#333333"}
edge_attr = {"fontsize": "9", "fontname": "Helvetica", "fontcolor": "#555555", "color": "#aaaaaa"}

def ca(bg="#f8f9fa", **kw):
    base = {"bgcolor": bg, "style": "rounded", "fontsize": "13", "fontname": "Helvetica Bold",
            "fontcolor": "#444444", "pencolor": "#cccccc", "penwidth": "2"}
    base.update(kw)
    return base

with Diagram(
    "",
    filename="architecture_png",
    outformat="png",
    show=False,
    graph_attr=graph_attr,
    edge_attr=edge_attr,
    node_attr=node_attr,
):
    user = Users("User")

    # ===== IMAGE PIPELINE (left branch) =====
    with Cluster("Image Pipeline (haus build)", graph_attr=ca("#e8f5e9")):
        floor_plan = Storage("Floor Plan\nPNG / JPEG")
        cli = Python("CLI")
        preprocess = Custom("OpenCV\nPreprocess", f"{ICO}/cv.png")
        extraction = Custom("NumPy\nExtraction", f"{ICO}/np.png")
        mesh = Custom("Trimesh\n3D Mesh", f"{ICO}/trimesh.png")
        pil = Custom("Pillow\nRender", f"{ICO}/pil.png")

    # ===== PIPELINE OUTPUTS =====
    with Cluster("Pipeline Output", graph_attr=ca("#fff3e0")):
        glb = Custom("model.glb", f"{ICO}/glb.png")
        vec = Storage("vector_clean.png")
        meta = Custom("metadata.json", f"{ICO}/json.png")

    # ===== BACKEND SERVER =====
    with Cluster("Backend Server (haus view)", graph_attr=ca("#e0f2f1")):
        starlette = Starlette("Starlette + Uvicorn")
        mcp = Custom("MCP Server\n30 Tools", f"{ICO}/mcp.png")
        layout = Custom("mcp-layout.json\n(live state)", f"{ICO}/json.png")
        starlette >> Edge(label="tool dispatch", color="#00897b") >> mcp >> Edge(color="#e65100") >> layout

    # ===== LLM PROVIDERS =====
    with Cluster("LLM Providers (configurable)", graph_attr=ca("#e3f2fd")):
        anthropic = Custom("Anthropic\nClaude", f"{ICO}/anthropic.png")
        openai = Custom("OpenAI\nGPT-4o", f"{ICO}/openai.png")
        gemini = Custom("Google\nGemini", f"{ICO}/gemini.png")

    # ===== 3D EDITOR FRONTEND =====
    with Cluster("3D Editor (viewer/  — Three.js)", graph_attr=ca("#e8eaf6")):
        threejs = Custom("Three.js Scene\nCamera + Renderer", f"{ICO}/3js.png")
        modules = Javascript("18 ES Modules\nFurniture  Walls  Selection\nUndo  Collision  Measure\nGrid  Camera  Overlay")
        io_sync = Javascript("I/O + MCP Sync\n(polls every 2s)")
        chat_ui = Custom("AI Chat Panel", f"{ICO}/ai.png")
        exports = Custom("Export\nGLB  SVG  JSON", f"{ICO}/svg_export.png")

    # ===== EDGES =====

    # user
    user >> Edge(label="upload image") >> floor_plan
    user >> Edge(label="browser") >> threejs

    # pipeline
    floor_plan >> cli >> preprocess >> extraction
    extraction >> mesh
    extraction >> pil

    # pipeline -> output
    mesh >> glb
    pil >> vec
    cli >> Edge(style="dashed") >> meta

    # editor internal
    threejs >> modules
    modules >> io_sync
    modules >> exports

    # GLB -> editor
    glb >> Edge(label="load", style="dashed") >> io_sync

    # editor <-> server sync
    io_sync >> Edge(label="POST /api/sync", color="#e65100") >> starlette
    layout >> Edge(label="poll 2s", color="#e65100", style="dashed") >> io_sync

    # chat
    chat_ui >> Edge(label="/api/chat", color="#5c6bc0") >> starlette

    # LLM calls
    starlette >> Edge(style="dashed", color="#1565c0") >> anthropic
    starlette >> Edge(style="dashed", color="#1565c0") >> openai
    starlette >> Edge(style="dashed", color="#1565c0") >> gemini
