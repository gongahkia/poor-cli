# haus

Pipeline to extract Singapore BTO floor plans from PDF brochures and convert them into Godot-ready GLB meshes.

## Architecture

```
PDF brochure
    |
    v
src/haus                 — PDF extraction -> GLB mesh (local CLI)
    |
    v
inference/modal_app.py   — CubiCasa5k segmentation + wall vectorization (Modal GPU endpoint)
    |
    v
Wall polygons + door/window openings -> 3D mesh (Phase 2)
```

---

## Local CLI — `haus`

Extracts a unit from a PDF and generates GLB meshes directly.

### Setup

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .
```

### Usage

```bash
haus extract \
  --pdf mount_pleasant_crest.pdf \
  --block 100A \
  --unit 127 \
  --storey-variant typical \
  --out out
```

**Outputs:**
- `out/block_100A_unit_127_default.glb`
- `out/block_100A_unit_127_white_flat.glb`
- `out/block_100A_unit_127.metadata.json`

**Notes:**
- Scale is calibrated from the page text `SCALE 0 2 4 6 8 10 METERS`
- Unit isolation is driven by the unit label (e.g. `UNIT 127`) and per-unit fill segmentation
- Diagonal units are kept in their true drawn orientation

---

## Modal Inference — CubiCasa5k

Deploys the pretrained [CubiCasa5k](https://github.com/CubiCasa/CubiCasa5k) hourglass segmentation model as a GPU-backed HTTP endpoint on [Modal](https://modal.com). Given a raster floor plan image it returns detected wall polygons, door/window openings, segmentation maps, and visual previews.

### Setup

```bash
uv pip install modal requests Pillow fastapi
modal setup        # authenticate with Modal (one-time)
```

### Download weights (one-time)

```bash
modal run inference/weights_setup.py
```

Weights (~200 MB) are stored in a Modal Volume named `cubicasa-weights`. If the Google Drive link is unavailable, upload manually:

```bash
modal volume put cubicasa-weights model_best_val_loss_var.pkl /model_best_val_loss_var.pkl
```

### Serve / deploy

```bash
modal serve inference/modal_app.py    # dev mode — live reload, ephemeral URL
modal deploy inference/modal_app.py  # production — stable URL
```

### Test

```bash
python inference/sample_request.py <endpoint-url> inference/sample.jpg
```

Saves three preview images to the current directory:
- `preview_seg.png` — room and icon segmentation colour map
- `preview_vector_clean.png` — detected walls and openings on white background
- `preview_vector_overlay.png` — same geometry overlaid on the input image

### Endpoint

`POST /predict` — `multipart/form-data`, field `image` (PNG or JPEG)

```json
{
  "walls":         [[[x,y],[x,y],[x,y],[x,y]], ...],
  "openings":      [{"polygon": [...], "class": 1, "label": "Window"}, ...],
  "wall_count":    25,
  "opening_count": 8,
  "segmentation_preview": "<base64 PNG>",
  "vector_clean":         "<base64 PNG>",
  "vector_overlay":       "<base64 PNG>",
  "inference_time_ms":    710,
  "postprocess_time_ms":  1096
}
```

**Model details:**
- Architecture: `hg_furukawa_original` (hourglass, 44-channel output)
- Channels: 0-20 junction heatmaps · 21-32 room segmentation (12 classes) · 33-43 icon segmentation (11 classes)
- GPU: T4 (configurable in `modal_app.py`)
- Checkpoint: `model_best_val_loss_var.pkl` from CubiCasa5k

---

## Phase status

| Phase | Description | Status |
|---|---|---|
| 1 | CubiCasa5k baseline inference on Singapore BTO plans | Done |
| 2 | Fine-tune on annotated Singapore BTO data | Planned |
| 3 | Wall polygon -> 3D mesh extrusion | Planned |
