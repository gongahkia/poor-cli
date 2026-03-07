### Task 1 (A) +infra | Philosophical Alignment

**PURPOSE** — The project has no virtual environment, no installed dependencies, and `uv` is not available on the system. Every other task is blocked because nothing can import or run. Without a working environment, the entire codebase is inert.

**WHAT TO DO**
1. Install `uv` via `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `pip install uv` if curl is unavailable).
2. Run `uv venv --python 3.11` in the project root `/home/gongahkia/Desktop/coding/projects/haus/` to create `.venv/`.
3. Activate the venv and run `uv pip install -e .` to install `haus` and its dependencies (`numpy>=1.26`, `opencv-python-headless>=4.10`) in editable mode.
4. Verify the install by running: `python -c "from haus.pipeline import run_vectorize; from haus.types import VectorizeConfig; print('OK')"`.
5. Verify the CLI entrypoint by running: `haus --help` and confirming the `vectorize` subcommand is listed.

**DONE WHEN**
- [ ] `.venv/` directory exists at project root with Python 3.11.
- [ ] `python -c "import cv2; import numpy; print('OK')"` prints `OK` inside the venv.
- [ ] `haus --help` prints usage text including the `vectorize` subcommand.
- [ ] `uv pip list` shows `haus` installed in editable mode.

---

### Task 2 (A) +infra | DX/Utility

**PURPOSE** — The 4 BTO floorplan photos (`photo_2026-03-07_10-34-41.jpg` through `photo_2026-03-07_10-35-09.jpg`) in the project root are the only test inputs available. They are untracked by git and excluded by `.gitignore` (which blocks `*.png` but not `*.jpg`). Tests need deterministic, committed fixture data to be reproducible.

**WHAT TO DO**
1. Create the directory `tests/fixtures/` under the project root.
2. Copy the 4 photos into `tests/fixtures/` with descriptive names:
   - `photo_2026-03-07_10-34-41.jpg` -> `tests/fixtures/bto_2room_orange.jpg`
   - `photo_2026-03-07_10-34-45.jpg` -> `tests/fixtures/bto_4room_yellow.jpg`
   - `photo_2026-03-07_10-34-49.jpg` -> `tests/fixtures/bto_3room_orange.jpg`
   - `photo_2026-03-07_10-35-09.jpg` -> `tests/fixtures/bto_4room_green.jpg`
3. Ensure `.gitignore` does not exclude `tests/fixtures/*.jpg`. The current `.gitignore` blocks `*.png` (which is fine — generated outputs) but not `*.jpg`, so no change should be needed. Verify by running `git status tests/fixtures/` and confirming the 4 files appear as untracked.
4. Stage and note the files are ready for commit (do not commit — that is the user's decision).

**DONE WHEN**
- [ ] `tests/fixtures/bto_2room_orange.jpg` exists and is a valid JPEG (non-zero size).
- [ ] `tests/fixtures/bto_4room_yellow.jpg` exists and is a valid JPEG.
- [ ] `tests/fixtures/bto_3room_orange.jpg` exists and is a valid JPEG.
- [ ] `tests/fixtures/bto_4room_green.jpg` exists and is a valid JPEG.
- [ ] `git status tests/fixtures/` shows all 4 files as untracked (not gitignored).

---

### Task 3 (A) +refactor | Philosophical Alignment

**PURPOSE** — `tests/test_pipeline.py` imports `run_extraction` and `ExtractionConfig` from `haus.pipeline` and `haus.types` respectively — neither exists. `tests/test_pdf.py` imports `haus.pdf` which does not exist as a module. Running `pytest` produces immediate `ImportError`s, giving false signals about project health and blocking CI.

**WHAT TO DO**
1. Delete `tests/test_pipeline.py` entirely (all 45 lines). It references a removed PDF-based API (`ExtractionConfig`, `run_extraction`, `run_extraction` return schema with `block`, `unit`, `source_page_number_1_based`, `variants`).
2. Delete `tests/test_pdf.py` entirely (all 28 lines). It references the non-existent `haus.pdf` module (`calibrate_scale`, `load_page_texts`, `select_floorplan_page`).
3. Create `tests/test_vectorize.py` with the following tests that exercise the actual API:
   - `test_extract_floor_plan_returns_walls()` — Load `tests/fixtures/bto_2room_orange.jpg` via `cv2.imread`, convert BGR->RGB, call `extract_floor_plan(img_rgb)`. Assert: returns a `FloorPlanData` with `len(data.walls) > 0`, `data.image_shape_hw` matches the image dimensions, `wall_mask` and `fill_mask` are numpy arrays of the same height/width.
   - `test_extract_floor_plan_detects_openings()` — Load `tests/fixtures/bto_4room_yellow.jpg`, call `extract_floor_plan`. Assert: `len(data.openings) > 0` (a 4-room unit has doors and windows).
   - `test_run_vectorize_produces_outputs(tmp_path)` — Create a `VectorizeConfig` with `image_path=Path("tests/fixtures/bto_3room_orange.jpg")`, `out_dir=tmp_path/"out"`, `debug_dir=tmp_path/"debug"`. Call `run_vectorize(cfg)`. Assert: `(tmp_path/"out"/"vector_clean.png").exists()`, `(tmp_path/"out"/"vector.metadata.json").exists()`, `(tmp_path/"debug"/"wall_mask.png").exists()`, `(tmp_path/"debug"/"fill_mask.png").exists()`, `(tmp_path/"debug"/"overlay.png").exists()`. Assert the returned metadata dict has keys `"walls"`, `"openings"`, `"scale"`.
   - `test_scale_estimation_produces_plausible_value()` — Load `tests/fixtures/bto_4room_green.jpg`, call `extract_floor_plan`. If `data.m_per_px` is not None, assert `0.005 < data.m_per_px < 0.1` (plausible range for HDB floor plan pixel scale).
4. Add `pytest` as a dev dependency: add `[project.optional-dependencies]` section to `pyproject.toml` with `dev = ["pytest>=8"]`.

**DONE WHEN**
- [ ] `tests/test_pipeline.py` does not exist.
- [ ] `tests/test_pdf.py` does not exist.
- [ ] `tests/test_vectorize.py` exists and contains 4 test functions.
- [ ] `pytest tests/test_vectorize.py` runs all 4 tests to completion (pass or xfail — no ImportError, no crash).
- [ ] `pyproject.toml` contains `[project.optional-dependencies]` with `pytest>=8` under `dev`.

---

### Task 4 (B) +refactor | Stability/Scaling

**PURPOSE** — `src/haus/extraction.py` uses ~15 unnamed magic numbers for thresholds (saturation, area, thickness, gap size, etc.). Tuning the CV pipeline for BTO accuracy requires understanding what each number controls. Without names, experimentation means grep-and-guess.

**WHAT TO DO**
1. In `src/haus/extraction.py`, the following constants already exist at module level (lines 55-58): `_WALL_HALF = 16`, `_MIN_WALL_LENGTH = 20`, `_STRUCTURAL_THICKNESS = 8`, `_MAX_WALL_THICKNESS = 25`. Keep these.
2. Extract the following unnamed literals into module-level constants immediately below the existing ones:
   - `_build_fill_mask` line 19: `35` -> `_FILL_SAT_MIN = 35` (minimum HSV saturation for fill detection)
   - `_build_fill_mask` line 19: `60` -> `_FILL_VAL_MIN = 60` (minimum HSV value for fill detection)
   - `_build_fill_mask` line 22: `7` -> `_FILL_VBRIDGE_HEIGHT = 7` (vertical bridging kernel height)
   - `_build_fill_mask` line 28: `500` -> `_FILL_MIN_COMPONENT_AREA = 500` (minimum connected component area for fill)
   - `_build_fill_mask` line 31: `1000` -> `_FILL_FALLBACK_THRESHOLD = 1000` (if total fill < this, use whole image)
   - `_solidify_fill` line 42: `100` -> `_SOLIDIFY_MIN_AREA = 100` (minimum component area for solidification)
   - `_extract_dark` line 68: `150` -> `_DARK_GRAY_THRESHOLD = 150` (grayscale threshold for "dark" pixels)
   - `_detect_columns` line 256: `120` -> `_COLUMN_GRAY_THRESHOLD = 120` (grayscale threshold for column detection)
   - `_detect_columns` line 264: `150` -> `_COLUMN_MIN_AREA = 150` (minimum column component area)
   - `_detect_columns` line 264: `6` -> `_COLUMN_MIN_DIM = 6` (minimum column bounding box dimension)
   - `_detect_columns` line 266: `4` -> `_COLUMN_MAX_ASPECT = 4` (maximum column aspect ratio)
   - `_detect_openings` line 310: `15` -> `_OPENING_MIN_GAP_PX = 15` (minimum opening gap in pixels)
   - `_detect_openings` line 310: `150` -> `_OPENING_MAX_GAP_PX = 150` (maximum opening gap in pixels)
   - `_detect_openings` line 318: `1.2` -> `_OPENING_DOOR_THRESHOLD_M = 1.2` (width threshold: < this = window, >= = door)
   - `_detect_openings` line 324: `20` -> `_OPENING_MAX_COUNT = 20` (hard cap on detected openings)
   - `_extract_wall_segments` line 234: `150` -> `_WALL_FRAGMENT_MIN_AREA = 150` (minimum area for wall mask fragments)
3. Replace every occurrence of the literal with the named constant. Do not change any logic or threshold values.

**DONE WHEN**
- [ ] All numeric literals listed above are replaced by named constants in `extraction.py`.
- [ ] No threshold logic has changed — `pytest tests/test_vectorize.py` produces identical results before and after.
- [ ] Every new constant has a one-line comment describing what it controls.

---

### Task 5 (B) +perf | Stability/Scaling

**PURPOSE** — `src/haus/render.py` lines 76-79 call `canvas.copy()` for every opening, allocating a full H x W x 3 array each time. For a 4-room HDB unit with 10+ openings on a 2000x2000 image, this is ~120 MB of unnecessary allocation. A single overlay pass eliminates this.

**WHAT TO DO**
1. In `src/haus/render.py`, replace the opening-rendering loop (lines 75-79):
   ```python
   for op in data.openings:
       color = _BGR_WINDOW if op.label == "Window" else _BGR_DOOR
       overlay = canvas.copy()
       cv2.rectangle(overlay, (op.x, op.y), (op.x + op.w, op.y + op.h), color, -1)
       cv2.addWeighted(overlay, 0.8, canvas, 0.2, 0, canvas)
   ```
   With a single-overlay approach:
   ```python
   if data.openings:
       overlay = canvas.copy()
       for op in data.openings:
           color = _BGR_WINDOW if op.label == "Window" else _BGR_DOOR
           cv2.rectangle(overlay, (op.x, op.y), (op.x + op.w, op.y + op.h), color, -1)
       cv2.addWeighted(overlay, 0.8, canvas, 0.2, 0, canvas)
   ```
2. This changes visual behaviour slightly (overlapping openings no longer compound opacity), but overlapping openings are physically impossible in a floor plan, so the result is equivalent.

**DONE WHEN**
- [ ] `render.py` contains exactly one `canvas.copy()` call in the openings section (or zero if no openings).
- [ ] `pytest tests/test_vectorize.py::test_run_vectorize_produces_outputs` still passes (vector_clean.png is generated).
- [ ] Visual spot-check: running `haus vectorize --image tests/fixtures/bto_4room_yellow.jpg --out /tmp/test_render` produces a `vector_clean.png` where openings are visible as colored rectangles.

---

### Task 6 (B) +refactor | Stability/Scaling

**PURPOSE** — `_build_fill_mask` in `src/haus/extraction.py` lines 31-33 silently replaces the fill mask with a full-image mask when fewer than 1000 saturated pixels are found. This is a heuristic for grayscale/unsaturated inputs, but it produces garbage wall detection because the entire image becomes the "search zone." A grayscale BTO scan or a photo with washed-out colors would trigger this silently.

**WHAT TO DO**
1. In `src/haus/extraction.py`, function `_build_fill_mask`, replace the silent fallback (lines 31-33):
   ```python
   if np.count_nonzero(fill) < 1000:
       h, w = img_rgb.shape[:2]
       fill = np.ones((h, w), dtype=np.uint8)
   ```
   With a version that emits a warning via `warnings.warn`:
   ```python
   if np.count_nonzero(fill) < _FILL_FALLBACK_THRESHOLD:
       import warnings
       warnings.warn(
           f"Fill mask has only {np.count_nonzero(fill)} saturated pixels "
           f"(threshold: {_FILL_FALLBACK_THRESHOLD}). "
           "Falling back to full-image search zone — wall detection may be inaccurate.",
           stacklevel=2,
       )
       h, w = img_rgb.shape[:2]
       fill = np.ones((h, w), dtype=np.uint8)
   ```
2. Move the `import warnings` to the top of the file (with the other stdlib imports after `from __future__ import annotations`).

**DONE WHEN**
- [ ] `_build_fill_mask` emits a `UserWarning` when the fill mask falls below threshold.
- [ ] The warning message includes the actual pixel count and the threshold value.
- [ ] Normal BTO images (the 4 test fixtures) do NOT trigger the warning — verify by running `python -W error -c "import cv2; from haus.extraction import extract_floor_plan; img = cv2.cvtColor(cv2.imread('tests/fixtures/bto_2room_orange.jpg'), cv2.COLOR_BGR2RGB); extract_floor_plan(img)"` (should not raise).

---

### Task 7 (B) +refactor | Stability/Scaling

**PURPOSE** — `_detect_openings` in `src/haus/extraction.py` line 324-325 hard-caps at 20 openings via `break`, silently discarding any beyond that. A large multi-unit plan or a plan with many windows could legitimately exceed 20. Silent data loss degrades downstream geometry.

**WHAT TO DO**
1. In `src/haus/extraction.py`, function `_detect_openings`, remove the hard break (lines 324-325):
   ```python
   if len(openings) >= 20:
       break
   ```
   Replace with a warning if the count seems unusually high (after the loop completes):
   ```python
   if len(openings) > _OPENING_MAX_COUNT:
       import warnings
       warnings.warn(
           f"Detected {len(openings)} openings (expected <= {_OPENING_MAX_COUNT}). "
           "Results may include false positives from non-opening gaps.",
           stacklevel=2,
       )
   ```
2. Move the check to after the `for` loop (after line 327), not inside it. All openings are now returned regardless.

**DONE WHEN**
- [ ] The `break` statement at former line 324-325 is removed.
- [ ] All detected openings are returned regardless of count.
- [ ] A `UserWarning` is emitted when the count exceeds `_OPENING_MAX_COUNT`.
- [ ] `pytest tests/test_vectorize.py` still passes.

---

### Task 8 (B) +security | Stability/Scaling

**PURPOSE** — `inference/modal_app.py` line 128 returns `traceback.format_exc()` in the JSON error response to any HTTP client. This exposes internal file paths, dependency versions, and code structure — an information disclosure risk for a production endpoint.

**WHAT TO DO**
1. In `inference/modal_app.py`, class `FloorplanInference`, method `predict` (lines 116-128), change the exception handler:
   ```python
   except Exception:
       return JSONResponse({"error": traceback.format_exc()}, status_code=500)
   ```
   To:
   ```python
   except Exception:
       traceback.print_exc()  # log server-side for debugging
       return JSONResponse({"error": "Internal server error"}, status_code=500)
   ```
2. Remove the `import traceback` at the top of `_predict` (line 124) if it's no longer used there. Keep it at function scope in `predict` since `traceback.print_exc()` still needs it.

**DONE WHEN**
- [ ] The `/predict` endpoint returns `{"error": "Internal server error"}` on unhandled exceptions, not a stack trace.
- [ ] The full traceback is printed to server-side logs (stdout/stderr) for debugging.
- [ ] No `traceback.format_exc()` output appears in any HTTP response body.

---

### Task 9 (B) +refactor | Stability/Scaling

**PURPOSE** — `CUBICASA_COMMIT = "c34440266665a11f4484eb06cd2e4b7d72ad76c1"` is hardcoded identically at `inference/modal_app.py:29` and `inference/weights_setup.py:16`. If one is updated without the other, the inference endpoint could load weights incompatible with the model source, causing silent failures.

**WHAT TO DO**
1. Create a new file `inference/_constants.py` with the single line:
   ```python
   CUBICASA_COMMIT = "c34440266665a11f4484eb06cd2e4b7d72ad76c1"
   ```
2. In `inference/modal_app.py`, remove line 29 (`CUBICASA_COMMIT = ...`) and add `from _constants import CUBICASA_COMMIT` at the top of the file (after the other imports). Note: Modal bundles the inference directory, so relative imports within `inference/` work when the image is built.
3. In `inference/weights_setup.py`, remove line 16 (`CUBICASA_COMMIT = ...`) and add `from _constants import CUBICASA_COMMIT` at the top.

**DONE WHEN**
- [ ] `CUBICASA_COMMIT` is defined in exactly one place: `inference/_constants.py`.
- [ ] Both `modal_app.py` and `weights_setup.py` import from `_constants`.
- [ ] `python -c "from inference._constants import CUBICASA_COMMIT; print(CUBICASA_COMMIT)"` prints the commit hash (run from project root).

---

### Task 10 (B) +docs | Philosophical Alignment

**PURPOSE** — The README documents a CLI command `haus extract --pdf ... --block ... --unit ...` that does not exist. The actual CLI only has `haus vectorize --image ... --out ...`. Developers and users who follow the README hit immediate failure. This erodes trust in the project.

**WHAT TO DO**
1. In `README.md`, replace the "Local CLI" section (lines 22-53) to document the actual `vectorize` command:
   - Command: `haus vectorize --image <path> --out <dir> [--debug-dir <dir>]`
   - Inputs: A raster floor plan image (PNG or JPEG) — e.g., a cropped BTO unit floor plan from an HDB brochure.
   - Outputs: `<out>/vector_clean.png` (wall polygons rendered on white background), `<out>/vector.metadata.json` (structured wall/opening/column data with scale estimation).
   - Optional: `--debug-dir` produces `wall_mask.png`, `fill_mask.png`, `overlay.png`.
2. Update the architecture diagram (lines 7-18) to reflect the current two-path architecture: local CV vectorization (`src/haus/`) and Modal CubiCasa5k inference (`inference/`), noting they are independent paths that will be unified.
3. Update the Phase status table (lines 124-131) to reflect current reality: Phase 1 (CubiCasa5k baseline) = Done, add a row for "Local CV vectorization" = Done, Phase 2 (Fine-tune) = Planned, Phase 3 (Wall polygon -> 3D mesh) = Planned.
4. Remove references to GLB output from the CLI section (GLB does not exist yet — it will be added in Task 12).

**DONE WHEN**
- [ ] `README.md` documents `haus vectorize` as the CLI command, not `haus extract`.
- [ ] The example command in README runs successfully: `haus vectorize --image tests/fixtures/bto_2room_orange.jpg --out /tmp/test_out`.
- [ ] No references to `--pdf`, `--block`, `--unit`, `--storey-variant` remain in README.
- [ ] Phase status table has a row for local CV vectorization.

---

### Task 11 (B) +feature | DX/Utility

**PURPOSE** — The current debug overlay (`pipeline.py` lines 104-109) only shows fill mask (red) and wall mask (green) blended on the source image. There is no way to visually verify whether the extracted wall segments, openings, and columns are geometrically correct — the user must read JSON coordinates manually. A labeled debug overlay is essential for tuning extraction accuracy.

**WHAT TO DO**
1. In `src/haus/pipeline.py`, in function `run_vectorize`, after the existing debug overlay block (lines 104-109), add a new debug image `segments_overlay.png`:
   - Start with a copy of `img_rgb` (BGR for cv2).
   - For each wall in `data.walls`, draw the wall segment as a line from `(w.x1, w.y1)` to `(w.x2, w.y2)` with thickness 2, color green `(0, 255, 0)` for structural, blue `(255, 0, 0)` for partition.
   - For each opening in `data.openings`, draw a rectangle `(o.x, o.y)` to `(o.x+o.w, o.y+o.h)` with thickness 2, color red `(0, 0, 255)` for Door, cyan `(255, 255, 0)` for Window, yellow `(0, 255, 255)` for Opening.
   - For each column in `data.columns`, draw a filled rectangle `(c.x, c.y)` to `(c.x+c.w, c.y+c.h)` in magenta `(255, 0, 255)`.
   - Save as `config.debug_dir / "segments_overlay.png"`.
2. Use `cv2.cvtColor(..., cv2.COLOR_RGB2BGR)` before saving since `img_rgb` is RGB but `cv2.imwrite` expects BGR.

**DONE WHEN**
- [ ] Running `haus vectorize --image tests/fixtures/bto_4room_green.jpg --out /tmp/t --debug-dir /tmp/d` produces `/tmp/d/segments_overlay.png`.
- [ ] The overlay visually shows colored lines for walls, rectangles for openings, and filled rectangles for columns on top of the source image.
- [ ] Existing debug outputs (`wall_mask.png`, `fill_mask.png`, `overlay.png`) are unaffected.

---

### Task 12 (B) +feature | Philosophical Alignment

**PURPOSE** — The project's core promise is 3D mesh output, but currently stops at 2D PNG rendering. Without GLB extrusion from the detected wall polygons, there is no path to the 3D web viewer end state. This task implements the wall-polygon-to-GLB pipeline using `trimesh`, which supports GLB export natively and has no heavy dependencies.

**WHAT TO DO**
1. Add `trimesh[easy]>=4.0` to the `dependencies` list in `pyproject.toml` (line 13). The `[easy]` extra pulls in `scipy` and other lightweight deps needed for mesh operations.
2. Create `src/haus/mesh.py` with a function `extrude_floor_plan(data: FloorPlanData, wall_height_m: float = 2.6) -> trimesh.Scene`:
   - For each wall in `data.walls`: take `wall.polygon_px` (4-point 2D rectangle), convert pixel coords to meters using `data.m_per_px` (if None, use a fallback of `0.02` m/px and log a warning). Extrude each polygon to `wall_height_m` using `trimesh.creation.extrude_polygon` with a `shapely.geometry.Polygon` from the 4 corners. Set the mesh color based on `wall.hdb_type`: shelter=(120,40,40,255), structural=(80,80,80,255), partition=(140,140,160,255), ferrolite=(180,180,180,255). Fallback for no hdb_type: structural=(80,80,80,255), partition=(140,140,160,255).
   - For each column in `data.columns`: create a box via `trimesh.creation.box(extents=[w*m_per_px, h*m_per_px, wall_height_m])` centered at the column center, color magenta (180,60,180,255).
   - For each opening in `data.openings`: create a thin box (0.05m deep) at the opening's bounding box position, height 2.1m for doors, 1.2m for windows (bottom at 0.9m), color blue (60,60,220,200) for windows, red (220,60,60,200) for doors. These are visual markers, not boolean subtractions (that's a Phase 2 refinement).
   - Combine all meshes into a `trimesh.Scene`. Set Y-up convention (Godot standard). The floor plan XY pixel coords map to scene XZ (horizontal plane), and extrusion goes along Y (up).
   - Return the scene.
3. Add a function `export_glb(scene: trimesh.Scene, out_path: Path) -> None` that calls `scene.export(file_type="glb")` and writes to `out_path`.
4. In `src/haus/pipeline.py`, import `extrude_floor_plan` and `export_glb` from `.mesh`. In `run_vectorize`, after rendering `vector_clean.png` (line 87), call `scene = extrude_floor_plan(data)` and `export_glb(scene, config.out_dir / "model.glb")`. Add `"output_glb": str(config.out_dir / "model.glb")` to the metadata dict.

**DONE WHEN**
- [ ] `src/haus/mesh.py` exists with `extrude_floor_plan` and `export_glb` functions.
- [ ] Running `haus vectorize --image tests/fixtures/bto_2room_orange.jpg --out /tmp/mesh_test` produces `/tmp/mesh_test/model.glb`.
- [ ] The GLB file is loadable by `trimesh.load("/tmp/mesh_test/model.glb")` without errors and contains at least 1 mesh.
- [ ] The GLB file is viewable in an online GLB viewer (e.g., https://gltf-viewer.donmccurdy.com/) and shows extruded wall geometry.
- [ ] `vector.metadata.json` includes the `output_glb` path.

---

### Task 13 (B) +feature | Philosophical Alignment

**PURPOSE** — The user needs a single command to go from image to mesh. Currently, `haus vectorize` produces a PNG and JSON but the GLB output (Task 12) is wired into the same command. This task adds a dedicated `haus build` command that makes the full pipeline explicit and adds control over mesh parameters (wall height, scale override).

**WHAT TO DO**
1. In `src/haus/cli.py`, function `_build_parser`, add a new subparser `build` (after the existing `vectorize` subparser, line 24):
   ```python
   build = subparsers.add_parser("build", help="Full pipeline: image -> vector + GLB mesh")
   build.add_argument("--image", required=True, type=Path, help="Path to floor plan image (PNG/JPEG)")
   build.add_argument("--out", required=True, type=Path, help="Output directory")
   build.add_argument("--debug-dir", type=Path, default=None, help="Optional debug artifact directory")
   build.add_argument("--wall-height", type=float, default=2.6, help="Wall extrusion height in meters (default: 2.6)")
   build.add_argument("--scale-override", type=float, default=None, help="Override m_per_px scale (bypass auto-detection)")
   ```
2. In the `main` function, add handling for `args.command == "build"` that calls `run_vectorize` (which now also produces GLB per Task 12). Pass wall_height and scale_override through to the pipeline. This requires adding `wall_height: float = 2.6` and `scale_override: float | None = None` fields to `VectorizeConfig` in `src/haus/types.py`.
3. The `build` command should print the metadata JSON to stdout (same as `vectorize`) and additionally print the GLB path to stderr for easy scripting.

**DONE WHEN**
- [ ] `haus build --help` shows all 5 arguments (image, out, debug-dir, wall-height, scale-override).
- [ ] `haus build --image tests/fixtures/bto_4room_green.jpg --out /tmp/build_test` produces both `vector_clean.png` and `model.glb` in the output directory.
- [ ] `haus build --image tests/fixtures/bto_2room_orange.jpg --out /tmp/build_test2 --wall-height 3.0` produces a GLB where walls are 3.0m tall (verifiable via `trimesh.load` and checking mesh bounds).
- [ ] `haus vectorize` still works as before (backward compatible).

---

### Task 14 (B) +feature | Philosophical Alignment

**PURPOSE** — The user's stated North Star end state is a 3D web app where users can view their BTO unit and place furniture. Without a web viewer that loads the GLB output, the pipeline has no user-facing frontend. This task creates a minimal Three.js viewer that loads GLB files and provides orbit controls, a ground plane, and basic furniture placement via drag-and-drop.

**WHAT TO DO**
1. Create `viewer/index.html` — a single-page app using Three.js (via CDN import map) with:
   - A full-viewport `<canvas>` with Three.js renderer.
   - `GLTFLoader` to load a GLB file. Default: load from `./model.glb` (relative path). Add a file input (`<input type="file" accept=".glb">`) to let users drag-drop or select their own GLB.
   - `OrbitControls` for camera rotation/zoom/pan.
   - A ground plane (grid helper) at Y=0.
   - Ambient light + directional light for visibility.
   - Camera positioned at a sensible default (e.g., 10m back, 8m up, looking at origin).
2. Add a furniture sidebar panel with 4-5 basic primitive furniture items (represented as colored boxes with labels):
   - Bed: 2.0m x 0.6m x 1.5m, light blue
   - Sofa: 2.0m x 0.8m x 0.8m, dark grey
   - Dining table: 1.2m x 0.75m x 0.8m, brown
   - Desk: 1.2m x 0.75m x 0.6m, tan
   - Wardrobe: 1.8m x 2.0m x 0.6m, dark wood
   Clicking a furniture item creates it at the center of the scene. The user can then drag it on the XZ plane using Three.js raycaster + drag controls.
3. Add a `viewer/README.md` with usage: `cd viewer && python -m http.server 8080` then open `http://localhost:8080`.
4. Wire into the CLI: in `src/haus/cli.py`, add a `view` subcommand: `haus view --glb <path>` that copies the GLB to `viewer/model.glb` and starts `python -m http.server 8080` in the `viewer/` directory, then opens the browser. Use `webbrowser.open` and `subprocess.Popen`.

**DONE WHEN**
- [ ] `viewer/index.html` exists and loads in a browser without errors (check browser console).
- [ ] Dropping a GLB file onto the file input renders the 3D mesh in the viewport.
- [ ] Orbit controls (rotate, zoom, pan) work.
- [ ] Clicking a furniture item in the sidebar spawns a colored box in the scene.
- [ ] Furniture items can be dragged on the XZ plane.
- [ ] `haus view --glb /tmp/mesh_test/model.glb` starts a local server and opens the browser.

---

### Task 15 (B) +infra | DX/Utility

**PURPOSE** — There is no automated quality gate. Code changes can break imports, types, or test assertions without anyone noticing until manual testing. A GitHub Actions CI pipeline running lint + type check + tests on every push prevents regressions.

**WHAT TO DO**
1. Add dev dependencies to `pyproject.toml` under `[project.optional-dependencies]`: `dev = ["pytest>=8", "ruff>=0.4", "pyright>=1.1"]`. (If Task 3 already added `pytest`, just add `ruff` and `pyright`.)
2. Create `.github/workflows/ci.yml`:
   ```yaml
   name: CI
   on: [push, pull_request]
   jobs:
     check:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: astral-sh/setup-uv@v3
         - run: uv venv --python 3.11
         - run: uv pip install -e ".[dev]"
         - run: ruff check src/ tests/
         - run: pyright src/
         - run: pytest tests/ -q
   ```
3. Create a minimal `pyrightconfig.json` at project root:
   ```json
   {
     "include": ["src"],
     "pythonVersion": "3.11",
     "typeCheckingMode": "basic"
   }
   ```
4. Verify locally: run `ruff check src/ tests/` and `pytest tests/ -q` and fix any lint errors that surface (likely: unused imports, line length). Do NOT change logic — only fix lint.

**DONE WHEN**
- [ ] `.github/workflows/ci.yml` exists with lint, type check, and test steps.
- [ ] `pyrightconfig.json` exists at project root.
- [ ] `ruff check src/ tests/` passes with zero errors locally.
- [ ] `pytest tests/ -q` passes locally.
- [ ] `pyproject.toml` lists `ruff>=0.4` and `pyright>=1.1` in dev dependencies.
