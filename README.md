# haus

Pipeline to vectorize Singapore BTO floor plan images and convert them into structured wall/opening data with optional 3D mesh output.

## Architecture

```
Raster floor plan image (PNG/JPEG)
    |
    +---> src/haus/          — Local CV vectorization pipeline (CLI)
    |         wall detection, opening detection, scale estimation
    |         -> vector_clean.png + metadata JSON
    |
    +---> inference/         — CubiCasa5k segmentation (Modal GPU endpoint)
              pretrained hourglass model, independent path
              -> wall polygons + door/window openings
              (will be unified with local path in future)
```

---

## Local CLI — `haus`

Vectorizes a raster floor plan image into classified wall segments, openings, and columns.

### Setup

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .
```

### Usage

```bash
haus vectorize --image <path> --out <dir> [--debug-dir <dir>]
```

**Example:**

```bash
haus vectorize \
  --image tests/fixtures/bto_2room_orange.jpg \
  --out out
```

**Outputs:**
- `<out>/vector_clean.png` — wall polygons rendered on white background
- `<out>/vector.metadata.json` — structured wall/opening/column data with scale estimation

**Optional:** `--debug-dir <dir>` produces debug artifacts:
- `wall_mask.png`, `fill_mask.png`, `overlay.png`

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
| 1b | Local CV vectorization pipeline | Done |
| 2 | Fine-tune on annotated Singapore BTO data | Planned |
| 3 | Wall polygon -> 3D mesh extrusion | Planned |
