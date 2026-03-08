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
    "bgcolor": "white",
    "pad": "0.5",
    "fontsize": "22",
    "fontname": "Helvetica",
    "fontcolor": "#1a1a1a",
    "ranksep": "0.9",
    "nodesep": "0.5",
    "splines": "curved",
    "dpi": "150",
}
node_attr = {
    "fontsize": "11",
    "fontname": "Helvetica",
    "fontcolor": "#333333",
}
edge_attr = {
    "fontsize": "9",
    "fontname": "Helvetica",
    "fontcolor": "#666666",
    "color": "#888888",
}

def ca(bg="#f8f9fa", **kw):
    base = {
        "bgcolor": bg, "style": "rounded",
        "fontsize": "13", "fontname": "Helvetica Bold",
        "fontcolor": "#333333", "pencolor": "#cccccc", "penwidth": "1.5",
    }
    base.update(kw)
    return base

with Diagram(
    "Haus — Floor Plan Vectorization & 3D Editor",
    filename="architecture_png",
    outformat="png",
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    edge_attr=edge_attr,
    node_attr=node_attr,
):
    # ---- top: user ----
    user = Users("User")

    # ---- row 1: input + LLM providers (side by side) ----
    with Cluster("Input", graph_attr=ca("#fff8e1")):
        floor_plan = Storage("BTO Floor Plan\n(PNG / JPEG)")

    with Cluster("LLM Providers", graph_attr=ca("#e3f2fd")):
        anthropic = Custom("Anthropic\nClaude", f"{ICO}/anthropic.png")
        openai = Custom("OpenAI\nGPT-4o", f"{ICO}/openai.png")
        gemini = Custom("Google\nGemini", f"{ICO}/gemini.png")

    # ---- row 2: backend ----
    with Cluster("Python Backend  (src/haus/)", graph_attr=ca("#e8f5e9")):
        with Cluster("Image Pipeline  (haus vectorize / haus build)", graph_attr=ca("#c8e6c9")):
            cli = Python("CLI\ncli.py")
            preprocess = Custom("Preprocess\nOpenCV", f"{ICO}/cv.png")
            extraction = Custom("Extract\nNumPy", f"{ICO}/np.png")
            mesh_gen = Custom("3D Mesh\nTrimesh", f"{ICO}/trimesh.png")
            render = Custom("Render\nPillow", f"{ICO}/pil.png")

        with Cluster("Web Server  (haus view)", graph_attr=ca("#c8e6c9")):
            chat_server = Starlette("Starlette\n+ Uvicorn")
            mcp_server = Custom("MCP Server\n30 Tools", f"{ICO}/mcp.png")

    # ---- row 3: data ----
    with Cluster("Data Layer  (file-based, no DB)", graph_attr=ca("#fff3e0")):
        layout_json = Custom("mcp-layout.json\nruntime sync", f"{ICO}/json.png")
        glb_file = Custom("model.glb\n3D mesh", f"{ICO}/glb.png")
        metadata = Custom("metadata.json\npipeline stats", f"{ICO}/json.png")
        vector_png = Storage("vector_clean.png\n2D output")

    # ---- row 4: frontend ----
    with Cluster("Frontend — 3D Editor  (viewer/)", graph_attr=ca("#e8eaf6")):
        editor = Javascript("editor.html")
        chat_panel = Custom("AI Chat\nPanel", f"{ICO}/ai.png")

        with Cluster("Three.js Core  (18 ES modules)", graph_attr=ca("#c5cae9")):
            scene = Custom("Scene / Camera\nRenderer", f"{ICO}/3js.png")
            furniture = Javascript("Furniture\n25 types")
            walls = Javascript("Walls\nDraw mode")
            selection = Javascript("Selection\nMulti + Drag")
            io_mod = Javascript("I/O\nMCP Sync 2s")
            undo = Javascript("Undo/Redo\n50-deep")
            collision = Javascript("Collision\nAABB")
            measure = Javascript("Measure\nDistance")

        with Cluster("Export", graph_attr=ca("#c5cae9")):
            svg_export = Custom("SVG\n2D Plan", f"{ICO}/svg_export.png")
            glb_export = Custom("GLB\n3D Scene", f"{ICO}/glb.png")

    # === edges ===

    # user -> input
    user >> Edge(label="uploads image", color="#666") >> floor_plan
    user >> Edge(label="opens browser", color="#666") >> editor

    # pipeline flow
    floor_plan >> Edge(color="#4caf50") >> cli
    cli >> Edge(color="#4caf50") >> preprocess
    preprocess >> Edge(color="#4caf50") >> extraction
    extraction >> Edge(label="FloorPlanData", color="#4caf50") >> mesh_gen
    extraction >> Edge(label="polygons", color="#4caf50") >> render

    # pipeline outputs
    mesh_gen >> Edge(color="#ff9800") >> glb_file
    render >> Edge(color="#ff9800") >> vector_png
    cli >> Edge(color="#ff9800", style="dashed") >> metadata

    # LLM connections
    chat_server >> Edge(style="dashed", color="#1565c0") >> anthropic
    chat_server >> Edge(style="dashed", color="#1565c0") >> openai
    chat_server >> Edge(style="dashed", color="#1565c0") >> gemini

    # server internal
    chat_server >> Edge(label="tool dispatch", color="#00897b") >> mcp_server

    # MCP sync cycle (orange)
    mcp_server >> Edge(color="#e65100") >> layout_json
    layout_json >> Edge(label="poll 2s", color="#e65100", style="dashed") >> io_mod
    io_mod >> Edge(label="POST sync", color="#e65100") >> chat_server

    # chat
    chat_panel >> Edge(label="/api/chat", color="#5c6bc0") >> chat_server

    # editor loads GLB
    glb_file >> Edge(label="load", style="dashed", color="#888") >> io_mod

    # scene graph
    editor >> scene
    scene >> furniture
    scene >> walls
    scene >> selection
    selection >> undo
    selection >> collision
    editor >> measure
    io_mod >> svg_export
    io_mod >> glb_export
