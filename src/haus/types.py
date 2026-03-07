from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import math

MetadataDict = Dict[str, object]


@dataclass(frozen=True)
class VectorizeConfig:
    image_path: Path
    out_dir: Path
    debug_dir: Optional[Path] = None


@dataclass(frozen=True)
class WallSegment:
    """An axis-aligned wall segment with classification."""
    x1: int
    y1: int
    x2: int
    y2: int
    thickness_px: float
    wall_type: str  # "structural" | "partition"
    thickness_m: Optional[float] = None       # real-world thickness
    hdb_type: Optional[str] = None            # "ferrolite" | "partition" | "structural" | "shelter"
    hdb_thickness_m: Optional[float] = None   # snapped HDB-standard thickness

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def is_horizontal(self) -> bool:
        return abs(self.y2 - self.y1) <= abs(self.x2 - self.x1)

    @property
    def polygon_px(self) -> list[tuple[float, float]]:
        """Wall rectangle: centerline offset +/- half-thickness perpendicular."""
        half = self.thickness_px / 2.0
        if self.is_horizontal:
            return [(self.x1, self.y1 - half), (self.x2, self.y2 - half),
                    (self.x2, self.y2 + half), (self.x1, self.y1 + half)]
        else:
            return [(self.x1 - half, self.y1), (self.x1 + half, self.y1),
                    (self.x2 + half, self.y2), (self.x2 - half, self.y2)]

    def to_dict(self) -> dict:
        d: dict = {
            "endpoints": [self.x1, self.y1, self.x2, self.y2],
            "thickness_px": round(self.thickness_px, 1),
            "wall_type": self.wall_type,
            "length_px": round(self.length, 1),
            "polygon_px": [[round(x, 1), round(y, 1)] for x, y in self.polygon_px],
        }
        if self.thickness_m is not None:
            d["thickness_m"] = round(self.thickness_m, 4)
        if self.hdb_type is not None:
            d["hdb_type"] = self.hdb_type
        if self.hdb_thickness_m is not None:
            d["hdb_thickness_m"] = self.hdb_thickness_m
        return d


@dataclass(frozen=True)
class Column:
    """A compact structural element (W1 column, pilaster)."""
    x: int
    y: int
    w: int
    h: int

    def to_dict(self) -> dict:
        return {"bbox_px": [self.x, self.y, self.w, self.h]}


@dataclass(frozen=True)
class Opening:
    """A detected opening (door or window)."""
    x: int
    y: int
    w: int
    h: int
    width_m: Optional[float]
    label: str  # "Window" | "Door" | "Opening"

    def to_dict(self) -> dict:
        return {
            "bbox_px": [self.x, self.y, self.w, self.h],
            "width_m": self.width_m,
            "label": self.label,
        }


@dataclass
class FloorPlanData:
    """Structured output from floor plan extraction."""
    walls: list[WallSegment] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)
    m_per_px: Optional[float] = None
    image_shape_hw: tuple[int, int] = (0, 0)
