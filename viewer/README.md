# haus viewer

Minimal Three.js floor plan viewer with furniture placement.

## Usage

```bash
cd viewer && python -m http.server 8080
```

Then open http://localhost:8080. Drop a `.glb` file or place `model.glb` in this directory.

Alternatively, use the CLI:

```bash
haus view --glb /path/to/model.glb
```

Use the `Load real layout` dropdown in the editor toolbar to load one of the
pre-vectorized BTO layouts from `corpus/library/` without running preprocessing.
