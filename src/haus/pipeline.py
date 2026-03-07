from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .extraction import extract_floor_plan
from .mesh import extrude_floor_plan, export_glb
from .render import render_vector_clean
from .types import FloorPlanData, MetadataDict, VectorizeConfig


def _to_serializable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_serializable(v) for v in value]
    return value


def _data_to_metadata(
    data: FloorPlanData,
    config: VectorizeConfig,
    vector_clean_path: Path,
    wall_mask_px: int,
    fill_mask_px: int,
) -> MetadataDict:
    structural = [w for w in data.walls if w.wall_type == "structural"]
    partitions = [w for w in data.walls if w.wall_type == "partition"]

    hdb_counts = {}
    for w in data.walls:
        if w.hdb_type is not None:
            hdb_counts[w.hdb_type] = hdb_counts.get(w.hdb_type, 0) + 1

    return {
        "source_image": str(config.image_path),
        "output_vector_clean": str(vector_clean_path),
        "image_shape_hw": list(data.image_shape_hw),
        "wall_mask_px": wall_mask_px,
        "fill_mask_px": fill_mask_px,
        "scale": {
            "m_per_px": data.m_per_px,
            "note": (
                "estimated from 150 mm structural wall assumption; ±30% uncertainty"
                if data.m_per_px is not None
                else "could not estimate scale — wall mask too sparse"
            ),
        },
        "walls": {
            "total_segments": len(data.walls),
            "structural_segments": len(structural),
            "partition_segments": len(partitions),
            "hdb_type_counts": hdb_counts,
            "segments": [w.to_dict() for w in data.walls],
        },
        "columns": [c.to_dict() for c in data.columns],
        "openings": {
            "total": len(data.openings),
            "by_type": {
                "Door": sum(1 for o in data.openings if o.label == "Door"),
                "Window": sum(1 for o in data.openings if o.label == "Window"),
                "Opening": sum(1 for o in data.openings if o.label == "Opening"),
            },
            "items": [o.to_dict() for o in data.openings],
        },
    }


def run_vectorize(config: VectorizeConfig) -> MetadataDict:
    config.out_dir.mkdir(parents=True, exist_ok=True)

    img_bgr = cv2.imread(str(config.image_path))
    if img_bgr is None:
        raise ValueError(f"Could not read image: {config.image_path}")
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    data, wall_mask, fill_mask = extract_floor_plan(img_rgb)

    vector_clean_path = config.out_dir / "vector_clean.png"
    render_vector_clean(data, vector_clean_path)

    glb_path = config.out_dir / "model.glb"
    scene = extrude_floor_plan(
        data,
        wall_height_m=getattr(config, "wall_height", 2.6),
        scale_override=getattr(config, "scale_override", None),
    )
    export_glb(scene, glb_path)

    metadata = _data_to_metadata(
        data, config, vector_clean_path,
        wall_mask_px=int(np.count_nonzero(wall_mask)),
        fill_mask_px=int(np.count_nonzero(fill_mask)),
    )

    metadata["output_glb"] = str(glb_path)

    metadata_path = config.out_dir / "vector.metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(_to_serializable(metadata), f, indent=2)

    if config.debug_dir is not None:
        config.debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(config.debug_dir / "wall_mask.png"), wall_mask * 255)
        cv2.imwrite(str(config.debug_dir / "fill_mask.png"), fill_mask * 255)

        overlay = img_rgb.copy()
        overlay2 = overlay.copy()
        overlay2[fill_mask > 0] = (255, 0, 0)
        overlay2[wall_mask > 0] = (0, 255, 0)
        blend = cv2.addWeighted(overlay, 0.65, overlay2, 0.35, 0.0)
        cv2.imwrite(str(config.debug_dir / "overlay.png"), cv2.cvtColor(blend, cv2.COLOR_RGB2BGR))

        seg_img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        for w in data.walls:
            color = (0, 255, 0) if w.wall_type == "structural" else (255, 0, 0)
            cv2.line(seg_img, (w.x1, w.y1), (w.x2, w.y2), color, 2)
        for o in data.openings:
            if o.label == "Door":
                color = (0, 0, 255)
            elif o.label == "Window":
                color = (255, 255, 0)
            else:
                color = (0, 255, 255)
            cv2.rectangle(seg_img, (o.x, o.y), (o.x + o.w, o.y + o.h), color, 2)
        for c in data.columns:
            cv2.rectangle(seg_img, (c.x, c.y), (c.x + c.w, c.y + c.h), (255, 0, 255), -1)
        cv2.imwrite(str(config.debug_dir / "segments_overlay.png"), seg_img)

    return metadata
