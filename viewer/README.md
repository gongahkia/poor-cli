# Haus Viewer

Three.js floor-plan editor with upload, vectorization review, furniture placement, planner chat, and export.

## Usage

```bash
haus view
```

Then upload a PNG/JPG/WebP floor plan in the editor, or load an existing JSON/GLB layout.

CLI preprocessing is still available:

```bash
haus build --image /path/to/floor-plan.png --out out/my-plan
haus view --glb out/my-plan/model.glb
```

Use the sample layout dropdown for bundled examples only; they are not the product's data dependency.
