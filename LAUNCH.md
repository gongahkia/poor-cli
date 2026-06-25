# Haus Launch Notes

## Positioning

**One-liner:** AI floor-plan workbench for uploaded apartment layouts.

**Longer:** Upload a floor-plan image, calibrate scale, extract editable 3D walls, then ask an AI agent to furnish and validate the layout through MCP tools.

## Demo Flow

1. Launch `haus view`.
2. Upload a PNG/JPG floor plan.
3. Enter a known pixel length and real-world length if available.
4. Review detected walls/openings and warnings.
5. Use quick prompt: `Furnish this apartment for a compact work-from-home setup.`
6. Apply plan, run layout score, export JSON/SVG/GLB.

## Messaging

Lead with:

- Upload any floor plan.
- Local-first editable 3D geometry.
- AI/MCP tools that operate on real objects.
- Spatial checks and measured exports.

Avoid leading with:

- BTO corpus coverage.
- Generic raster-to-vector claims.
- Construction drawings, permits, or compliance certification.
- Photorealistic AI renders.
- Deprecated hackathon workflows.

## Audiences

- Apartment owners testing furniture layouts before renovation or move-in.
- Designers who want fast concept layouts from client floor plans.
- AI/MCP developers who want a visual agent demo with real state mutation.

## Limits

Scale is approximate unless calibrated. Extraction can fail on noisy scans, low contrast, or heavily annotated plans. Haus should fall back to image overlay plus manual wall drawing rather than overclaiming.
