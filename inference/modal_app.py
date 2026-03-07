"""
CubiCasa5k Modal Inference Endpoint — Phase 1

Deploys the pretrained CubiCasa5k hourglass segmentation model as an HTTP
endpoint. POST /predict accepts a floorplan image and returns:
  - Room/icon segmentation maps (for reference)
  - Wall polygons and door/window openings extracted by the CubiCasa
    post-processing pipeline (the output we actually care about)
  - A vector overlay PNG showing detected walls and openings

Usage:
    modal serve inference/modal_app.py    # dev mode with live reload
    modal deploy inference/modal_app.py  # stable production URL
"""

import warnings
import base64
import time
import io

import modal
from fastapi import Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Modal image — PyTorch base + dependencies + CubiCasa5k source
# ---------------------------------------------------------------------------

CUBICASA_COMMIT = "c34440266665a11f4484eb06cd2e4b7d72ad76c1"

cubicasa_image = (
    modal.Image.from_registry("pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime")
    .apt_install(["git"])
    .pip_install([
        "numpy",
        "scipy",
        "scikit-image",
        "Pillow",
        "shapely",
        "svgpathtools",
        "svgwrite",
        "gdown",
        "matplotlib",
        "fastapi[standard]",  # required for web endpoints (includes python-multipart)
    ])
    .run_commands(
        f"git clone https://github.com/CubiCasa/CubiCasa5k /cubicasa",
        f"cd /cubicasa && git checkout {CUBICASA_COMMIT}",
    )
    .env({"PYTHONPATH": "/cubicasa"})
)

# ---------------------------------------------------------------------------
# Modal app + volume
# ---------------------------------------------------------------------------

app = modal.App("cubicasa-inference", image=cubicasa_image)

volume = modal.Volume.from_name("cubicasa-weights", create_if_missing=True)

# ---------------------------------------------------------------------------
# Class label maps
#
# Channel layout (44-channel checkpoint):
#   0–20  : junction heatmaps (21 channels)
#   21–32 : room segmentation logits (12 classes)
#   33–43 : icon segmentation logits (11 classes)
# ---------------------------------------------------------------------------

ROOM_CLASSES = {
    0: "Background", 1: "Outdoor",   2: "Wall",    3: "Kitchen",
    4: "Living Room", 5: "Bed Room", 6: "Bath",     7: "Entry",
    8: "Railing",     9: "Storage",  10: "Garage",  11: "Undefined",
}

ICON_CLASSES = {
    0: "No Icon",  1: "Window",   2: "Door",      3: "Closet",
    4: "Elec. Appl.", 5: "Toilet", 6: "Sink",     7: "Sauna Bench",
    8: "Fire Place",  9: "Bathtub", 10: "Chimney",
}

# Post-processing channel split
_SPLIT = [21, 12, 11]


# ---------------------------------------------------------------------------
# Inference class
# ---------------------------------------------------------------------------

@app.cls(
    gpu="T4",  # cost-efficient for Phase 1; bump to A10G if needed
    volumes={"/weights": volume},
)
class FloorplanInference:
    """Stateful inference class — model is loaded once on cold start."""

    @modal.enter()
    def load_model(self) -> None:
        """Load and warm up the model. Called once per container lifecycle."""
        import torch
        from floortrans.models.hg_furukawa_original import hg_furukawa_original as HGModel

        warnings.filterwarnings("ignore", message=".*align_corners.*", category=UserWarning)

        checkpoint = torch.load("/weights/model_best_val_loss_var.pkl", map_location="cpu")

        # Instantiate directly — skipping init_weights(), which copies from
        # model_1427.pth (saved with 51 channels) and would fail on our 44-channel
        # build. We overwrite all weights from the checkpoint immediately anyway.
        model = HGModel(n_classes=44)
        model.load_state_dict(checkpoint["model_state"])
        model.eval().cuda()

        self.model = model

    @modal.fastapi_endpoint(method="POST")
    async def predict(self, request: Request) -> JSONResponse:
        """
        POST /predict — multipart/form-data with field 'image' (PNG or JPEG).

        Returns segmentation maps, extracted wall/opening polygons,
        a segmentation preview, and a vector overlay PNG.
        """
        import traceback
        try:
            return await self._predict(request)
        except Exception:
            traceback.print_exc()
            return JSONResponse({"error": "Internal server error"}, status_code=500)

    async def _predict(self, request: Request) -> JSONResponse:
        import torch
        import numpy as np
        from PIL import Image

        # --- Read multipart form ---
        form = await request.form()
        image_file = form.get("image")
        if image_file is None:
            return JSONResponse({"error": "Missing 'image' field in form data"}, status_code=400)
        image_bytes = await image_file.read()

        # --- Preprocess ---
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Pad to square, resize to 256×256
        w, h = pil_img.size
        side = max(w, h)
        padded = Image.new("RGB", (side, side), (255, 255, 255))
        padded.paste(pil_img, ((side - w) // 2, (side - h) // 2))
        resized = padded.resize((256, 256), Image.BILINEAR)

        img_array = np.array(resized, dtype=np.float32) / 255.0
        image_tensor = (
            torch.from_numpy(img_array)
            .permute(2, 0, 1)
            .unsqueeze(0)   # → (1, 3, 256, 256)
            .cuda()
        )

        # --- Inference ---
        t0 = time.perf_counter()
        with torch.no_grad():
            outputs = self.model(image_tensor)  # (1, 44, 256, 256)
        inference_ms = int((time.perf_counter() - t0) * 1000)

        # --- Segmentation argmax (for the segmentation preview) ---
        room_np = torch.argmax(outputs[:, 21:33], dim=1)[0].cpu().numpy().astype(np.int32)
        icon_np = torch.argmax(outputs[:, 33:44], dim=1)[0].cpu().numpy().astype(np.int32)

        # --- Vector post-processing: walls + openings only ---
        t1 = time.perf_counter()
        walls, openings = _extract_walls_and_openings(outputs)
        postprocess_ms = int((time.perf_counter() - t1) * 1000)

        # --- Render previews ---
        seg_preview                    = _render_seg_preview(room_np, icon_np)
        vector_clean, vector_overlay   = _render_vector_preview(np.array(resized), walls, openings)

        return JSONResponse({
            # Segmentation maps
            "room_map":    room_np.tolist(),
            "icon_map":    icon_np.tolist(),
            "room_classes": ROOM_CLASSES,
            "icon_classes": ICON_CLASSES,
            # Vector geometry
            "walls":         [w.tolist() for w in walls],
            "openings":      openings,
            "wall_count":    len(walls),
            "opening_count": len(openings),
            # Previews
            "segmentation_preview": seg_preview,
            "vector_clean":         vector_clean,    # geometry on white background
            "vector_overlay":       vector_overlay,  # geometry over original image
            # Timing
            "inference_time_ms":   inference_ms,
            "postprocess_time_ms": postprocess_ms,
        })


# ---------------------------------------------------------------------------
# Post-processing: extract wall rectangles + door/window openings
# ---------------------------------------------------------------------------

def _patch_scipy_mode():
    """
    scipy ≥ 1.9 changed stats.mode to return scalars instead of 1-element
    arrays, breaking CubiCasa's `stats.mode(widths).mode[0]` calls.
    Monkey-patch to restore the old array-returning behaviour.
    """
    import numpy as np
    import scipy.stats as scipy_stats
    from collections import namedtuple

    _ModeResult = namedtuple("ModeResult", ["mode", "count"])
    _original = scipy_stats.mode

    def _compat_mode(a, axis=0, **kwargs):
        kwargs.pop("keepdims", None)  # keepdims added in 1.9, not in old API
        result = _original(a, axis=axis, **kwargs)
        mode_val  = result.mode
        count_val = result.count
        if not hasattr(mode_val, "__len__"):
            mode_val  = np.array([mode_val])
            count_val = np.array([count_val])
        return _ModeResult(mode_val, count_val)

    scipy_stats.mode = _compat_mode


def _extract_walls_and_openings(outputs):
    """
    Run CubiCasa's vectorization pipeline on the raw model output.

    Returns:
        walls    — list of np.ndarray (4, 2) int pixel coords, one per wall
        openings — list of dicts {polygon, class, label} for doors & windows
    """
    _patch_scipy_mode()
    from floortrans.post_prosessing import get_polygons, split_prediction

    # split_prediction upsamples to (256, 256), applies softmax on room/icon
    # channels, and returns (heatmaps, rooms, icons) as numpy arrays.
    predictions = split_prediction(outputs.cpu(), (256, 256), _SPLIT)

    # get_polygons returns all detected primitives concatenated:
    #   polygons : (N, 4, 2) int pixel coords
    #   types    : list of {'type': 'wall'/'icon', 'class': int, ...}
    # room_polygons / room_types are Shapely objects we don't need here.
    polygons, types, _room_polys, _room_types = get_polygons(
        predictions, threshold=0.2, all_opening_types=[1, 2]
    )

    walls = []
    openings = []

    for poly, t in zip(polygons, types):
        if t["type"] == "wall":
            walls.append(poly)
        elif int(t.get("class", -1)) in (1, 2):   # 1=Window, 2=Door
            openings.append({
                "polygon": poly.tolist(),
                "class":   int(t["class"]),
                "label":   ICON_CLASSES[int(t["class"])],
            })

    return walls, openings


# ---------------------------------------------------------------------------
# Visualization helpers
# ---------------------------------------------------------------------------

def _render_seg_preview(room_np, icon_np) -> str:
    """Side-by-side room/icon segmentation using CubiCasa furukawa palettes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    room_cmap = mcolors.ListedColormap([
        "#696969", "#b3de69", "#ffffb3", "#8dd3c7", "#fdb462",
        "#fccde5", "#80b1d3", "#d9d9d9", "#fb8072", "#577a4d",
        "white", "#000000",
    ])
    icon_cmap = mcolors.ListedColormap([
        "#ede676", "#8dd3c7", "#b15928", "#fdb462", "#ffff99",
        "#fccde5", "#80b1d3", "#d9d9d9", "#fb8072", "#696969", "#577a4d",
    ])

    fig, axes = plt.subplots(1, 2, figsize=(10, 5), tight_layout=True)
    axes[0].imshow(room_np, cmap=room_cmap, vmin=0, vmax=11, interpolation="nearest")
    axes[0].set_title("Room Segmentation", fontsize=12)
    axes[0].axis("off")
    axes[1].imshow(icon_np, cmap=icon_cmap, vmin=0, vmax=10, interpolation="nearest")
    axes[1].set_title("Icon Detection", fontsize=12)
    axes[1].axis("off")

    return _fig_to_b64(fig)


def _render_vector_preview(img_np, walls, openings):
    """
    Returns two base64 PNGs as a tuple:
      [0] clean — vector geometry on a plain white background
      [1] overlay — same geometry composited over the original image

    Walls = dark grey, Windows = blue, Doors = red.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Polygon as MplPolygon

    H, W = img_np.shape[:2]
    n_walls   = len(walls)
    n_windows = sum(1 for o in openings if o["class"] == 1)
    n_doors   = sum(1 for o in openings if o["class"] == 2)
    title     = f"{n_walls} walls · {n_windows} windows · {n_doors} doors"

    legend_handles = [
        mpatches.Patch(facecolor="#2c2c2c", label="Wall"),
        mpatches.Patch(facecolor="#3a9ee4", label="Window"),
        mpatches.Patch(facecolor="#e84c3d", label="Door"),
    ]

    def _add_patches(ax):
        for poly in walls:
            ax.add_patch(MplPolygon(
                poly[:, :2], closed=True,
                facecolor="#2c2c2c", edgecolor="#000000", linewidth=1.0,
            ))
        for opening in openings:
            color = "#3a9ee4" if opening["class"] == 1 else "#e84c3d"
            ax.add_patch(MplPolygon(
                opening["polygon"], closed=True,
                facecolor=color, edgecolor=color, linewidth=1.5, alpha=0.85,
            ))
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis("off")
        ax.legend(handles=legend_handles, loc="lower right",
                  fontsize=9, framealpha=0.9)
        ax.set_title(title, fontsize=10)

    # --- Clean: white background ---
    fig_clean, ax_clean = plt.subplots(figsize=(7, 7), tight_layout=True)
    ax_clean.set_facecolor("white")
    fig_clean.patch.set_facecolor("white")
    _add_patches(ax_clean)
    clean_b64 = _fig_to_b64(fig_clean)

    # --- Overlay: original image as background ---
    fig_over, ax_over = plt.subplots(figsize=(7, 7), tight_layout=True)
    ax_over.imshow(img_np)
    for poly in walls:
        ax_over.add_patch(MplPolygon(
            poly[:, :2], closed=True,
            facecolor="#1a1a1a", alpha=0.40,
            edgecolor="#000000", linewidth=1.0,
        ))
    for opening in openings:
        color = "#3a9ee4" if opening["class"] == 1 else "#e84c3d"
        ax_over.add_patch(MplPolygon(
            opening["polygon"], closed=True,
            facecolor=color, edgecolor=color, linewidth=1.5, alpha=0.70,
        ))
    ax_over.set_xlim(0, W)
    ax_over.set_ylim(H, 0)
    ax_over.axis("off")
    ax_over.legend(handles=legend_handles, loc="lower right",
                   fontsize=9, framealpha=0.9)
    ax_over.set_title(title, fontsize=10)
    overlay_b64 = _fig_to_b64(fig_over)

    return clean_b64, overlay_b64


def _fig_to_b64(fig) -> str:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
