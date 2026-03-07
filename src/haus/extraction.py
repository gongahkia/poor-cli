from __future__ import annotations

import math

import cv2
import numpy as np

from .types import Column, FloorPlanData, Opening, WallSegment


# ---------------------------------------------------------------------------
# Fill detection
# ---------------------------------------------------------------------------

def _build_fill_mask(img_rgb: np.ndarray) -> np.ndarray:
    """Union of all saturated connected components (>= 500 px)."""
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    saturated = (
        (hsv[:, :, 1] > _FILL_SAT_MIN) & (hsv[:, :, 2] > _FILL_VAL_MIN)
    ).astype(np.uint8)

    k_vbridge = np.ones((_FILL_VBRIDGE_HEIGHT, 1), np.uint8)
    saturated = cv2.morphologyEx(saturated, cv2.MORPH_CLOSE, k_vbridge, iterations=1)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(saturated, 8)
    fill = np.zeros_like(saturated)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) >= _FILL_MIN_COMPONENT_AREA:
            fill[labels == i] = 1

    if np.count_nonzero(fill) < _FILL_FALLBACK_THRESHOLD:
        h, w = img_rgb.shape[:2]
        fill = np.ones((h, w), dtype=np.uint8)
    return fill


def _solidify_fill(fill_mask: np.ndarray) -> np.ndarray:
    """Fill interior holes via outer contour drawing per component."""
    num, labels, stats, _ = cv2.connectedComponentsWithStats(fill_mask, 8)
    solid = np.zeros_like(fill_mask)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) < _SOLIDIFY_MIN_AREA:
            continue
        comp = (labels == i).astype(np.uint8)
        contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            cv2.drawContours(solid, [c], -1, 1, thickness=-1)
    return solid


# ---------------------------------------------------------------------------
# Dark pixel extraction (search zone from fill mask)
# ---------------------------------------------------------------------------

_FILL_SAT_MIN = 35              # minimum HSV saturation for fill detection
_FILL_VAL_MIN = 60              # minimum HSV value for fill detection
_FILL_VBRIDGE_HEIGHT = 7        # vertical bridging kernel height
_FILL_MIN_COMPONENT_AREA = 500  # minimum connected component area for fill
_FILL_FALLBACK_THRESHOLD = 1000 # if total fill < this, use whole image
_SOLIDIFY_MIN_AREA = 100        # minimum component area for solidification
_DARK_GRAY_THRESHOLD = 150      # grayscale threshold for "dark" pixels
_COLUMN_GRAY_THRESHOLD = 120    # grayscale threshold for column detection
_COLUMN_MIN_AREA = 150          # minimum column component area
_COLUMN_MIN_DIM = 6             # minimum column bounding box dimension
_COLUMN_MAX_ASPECT = 4          # maximum column aspect ratio
_OPENING_MIN_GAP_PX = 15        # minimum opening gap in pixels
_OPENING_MAX_GAP_PX = 150       # maximum opening gap in pixels
_OPENING_DOOR_THRESHOLD_M = 1.2 # width threshold: < this = window, >= = door
_OPENING_MAX_COUNT = 20         # hard cap on detected openings
_WALL_FRAGMENT_MIN_AREA = 150   # minimum area for wall mask fragments

_WALL_HALF = 16
_MIN_WALL_LENGTH = 20
_STRUCTURAL_THICKNESS = 8  # px — walls >= this are structural
_MAX_WALL_THICKNESS = 25   # px — bounding-box thickness hard cap


def _extract_dark(img_rgb: np.ndarray, fill_mask: np.ndarray) -> np.ndarray:
    """Extract dark pixels within the floor plan interior search zone."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    fill_solid = _solidify_fill(fill_mask)
    k_wall = np.ones((_WALL_HALF * 2 + 1, _WALL_HALF * 2 + 1), np.uint8)
    fill_dilated = cv2.dilate(fill_solid, k_wall, iterations=1)

    dark = ((gray < _DARK_GRAY_THRESHOLD) & (fill_dilated > 0)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    return dark


# ---------------------------------------------------------------------------
# Wall segment extraction — directional open component analysis
# ---------------------------------------------------------------------------

def _measure_wall_in_blob(
    comp_mask: np.ndarray,
    horizontal: bool,
) -> tuple[float, float] | None:
    """Find the actual wall within a bloated component via projection peak.

    Projects the component perpendicular to the wall direction, smooths the
    profile to merge double-line wall representations into a single peak,
    then finds the densest band.

    Returns (thickness, center_offset) where center_offset is the
    perpendicular position of the wall center relative to the ROI top/left,
    or None if no clear wall peak is found.
    """
    if horizontal:
        profile = comp_mask.sum(axis=1).astype(float)
    else:
        profile = comp_mask.sum(axis=0).astype(float)

    if profile.max() == 0:
        return None

    # Smooth profile to merge double-line wall representations.
    # A boxcar of ~15px bridges the gap between two parallel wall lines
    # (typically 3-8px line + 3-8px gap + 3-8px line).
    smooth_w = min(15, len(profile))
    kernel = np.ones(smooth_w) / smooth_w
    smoothed = np.convolve(profile, kernel, mode="same")

    # Find peak of smoothed profile
    peak_idx = int(np.argmax(smoothed))
    peak_val = smoothed[peak_idx]

    # Expand outward from peak while smoothed density stays above 30% of peak.
    # Lower threshold (vs 50%) captures the full double-line wall extent.
    threshold = peak_val * 0.3
    lo = peak_idx
    hi = peak_idx
    while lo > 0 and smoothed[lo - 1] >= threshold:
        lo -= 1
    while hi < len(profile) - 1 and smoothed[hi + 1] >= threshold:
        hi += 1

    thickness = float(hi - lo + 1)
    center = (lo + hi) / 2.0

    if thickness > _MAX_WALL_THICKNESS:
        # Smoothing captured too much — fall back to raw profile peak
        peak_idx = int(np.argmax(profile))
        peak_val = profile[peak_idx]
        threshold = peak_val * 0.5
        lo = peak_idx
        hi = peak_idx
        while lo > 0 and profile[lo - 1] >= threshold:
            lo -= 1
        while hi < len(profile) - 1 and profile[hi + 1] >= threshold:
            hi += 1
        thickness = float(hi - lo + 1)
        center = (lo + hi) / 2.0

    return thickness, center


def _extract_wall_segments(
    dark: np.ndarray,
    *,
    min_length: int = _MIN_WALL_LENGTH,
    min_area: int = 100,
) -> tuple[list[WallSegment], np.ndarray]:
    """Extract classified wall segments via directional morphological open.

    Each axis direction (horizontal, vertical) is opened separately.
    Connected components of each opened mask become wall segment candidates.
    Thickness is measured via median perpendicular cross-section rather than
    raw bounding-box short axis, to handle merged components accurately.

    Returns (segments, wall_mask) where wall_mask is the union of all
    wall pixels (for debug/scale estimation).
    """
    k_h = np.ones((1, min_length), np.uint8)
    k_v = np.ones((min_length, 1), np.uint8)
    horiz = cv2.morphologyEx(dark, cv2.MORPH_OPEN, k_h)
    vert = cv2.morphologyEx(dark, cv2.MORPH_OPEN, k_v)

    segments: list[WallSegment] = []

    # Horizontal wall segments
    num_h, labels_h, stats_h, _ = cv2.connectedComponentsWithStats(horiz, 8)
    for i in range(1, num_h):
        area = int(stats_h[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats_h[i, cv2.CC_STAT_LEFT])
        y = int(stats_h[i, cv2.CC_STAT_TOP])
        w = int(stats_h[i, cv2.CC_STAT_WIDTH])
        h = int(stats_h[i, cv2.CC_STAT_HEIGHT])
        if w < min_length:
            continue
        if h <= _MAX_WALL_THICKNESS:
            # Normal component — use bounding box
            thickness = float(h)
            cy = y + h // 2
        else:
            # Bloated component — find wall peak within the blob
            comp_mask = (labels_h[y:y + h, x:x + w] == i).astype(np.uint8)
            result = _measure_wall_in_blob(comp_mask, horizontal=True)
            if result is None:
                continue
            thickness, center_off = result
            if thickness < 1 or thickness > _MAX_WALL_THICKNESS:
                continue
            cy = y + int(round(center_off))
        wall_type = "structural" if thickness >= _STRUCTURAL_THICKNESS else "partition"
        segments.append(WallSegment(
            x1=x, y1=cy, x2=x + w, y2=cy,
            thickness_px=thickness, wall_type=wall_type,
        ))

    # Vertical wall segments
    num_v, labels_v, stats_v, _ = cv2.connectedComponentsWithStats(vert, 8)
    for i in range(1, num_v):
        area = int(stats_v[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats_v[i, cv2.CC_STAT_LEFT])
        y = int(stats_v[i, cv2.CC_STAT_TOP])
        w = int(stats_v[i, cv2.CC_STAT_WIDTH])
        h = int(stats_v[i, cv2.CC_STAT_HEIGHT])
        if h < min_length:
            continue
        if w <= _MAX_WALL_THICKNESS:
            thickness = float(w)
            cx = x + w // 2
        else:
            comp_mask = (labels_v[y:y + h, x:x + w] == i).astype(np.uint8)
            result = _measure_wall_in_blob(comp_mask, horizontal=False)
            if result is None:
                continue
            thickness, center_off = result
            if thickness < 1 or thickness > _MAX_WALL_THICKNESS:
                continue
            cx = x + int(round(center_off))
        wall_type = "structural" if thickness >= _STRUCTURAL_THICKNESS else "partition"
        segments.append(WallSegment(
            x1=cx, y1=y, x2=cx, y2=y + h,
            thickness_px=thickness, wall_type=wall_type,
        ))

    # Build wall mask as union of horizontal and vertical features
    wall_mask = cv2.bitwise_or(horiz, vert)
    # Recapture dark pixels near the detected features (for crisp edges)
    wall_region = cv2.dilate(wall_mask, np.ones((5, 5), np.uint8), iterations=1)
    wall_mask = ((dark > 0) & (wall_region > 0)).astype(np.uint8)

    # Remove small isolated fragments
    num_w, labels_w, stats_w, _ = cv2.connectedComponentsWithStats(wall_mask, 8)
    for i in range(1, num_w):
        if int(stats_w[i, cv2.CC_STAT_AREA]) < _WALL_FRAGMENT_MIN_AREA:
            wall_mask[labels_w == i] = 0

    return segments, wall_mask


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

def _detect_columns(
    img_rgb: np.ndarray,
    fill_mask: np.ndarray,
    wall_mask: np.ndarray,
) -> list[Column]:
    """Detect compact structural elements (W1 columns) in the outer boundary."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    fill_solid = _solidify_fill(fill_mask)
    k_wall = np.ones((_WALL_HALF * 2 + 1, _WALL_HALF * 2 + 1), np.uint8)
    fill_dilated = cv2.dilate(fill_solid, k_wall, iterations=1)

    outer_band = ((fill_dilated > 0) & (fill_solid == 0)).astype(np.uint8)
    residual = ((gray < _COLUMN_GRAY_THRESHOLD).astype(np.uint8)) & outer_band & (wall_mask == 0)

    columns: list[Column] = []
    num, labels, stats, _ = cv2.connectedComponentsWithStats(residual, 8)
    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if area >= _COLUMN_MIN_AREA and min(bw, bh) >= _COLUMN_MIN_DIM:
            aspect = max(bw, bh) / max(min(bw, bh), 1)
            if aspect < _COLUMN_MAX_ASPECT:
                columns.append(Column(
                    x=int(stats[i, cv2.CC_STAT_LEFT]),
                    y=int(stats[i, cv2.CC_STAT_TOP]),
                    w=bw, h=bh,
                ))
    return columns


# ---------------------------------------------------------------------------
# Opening detection
# ---------------------------------------------------------------------------

def _detect_openings(
    wall_mask: np.ndarray,
    m_per_px: float | None,
) -> list[Opening]:
    """Detect exterior openings via outer-contour gap analysis."""
    if np.count_nonzero(wall_mask) < 200:
        return []

    h, w = wall_mask.shape
    k5 = np.ones((5, 5), np.uint8)
    k3 = np.ones((3, 3), np.uint8)

    wall_dilated = cv2.dilate(wall_mask.astype(np.uint8), k5, iterations=4)
    outer_contours, _ = cv2.findContours(wall_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not outer_contours:
        return []

    main_contour = max(outer_contours, key=cv2.contourArea)
    perimeter_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.drawContours(perimeter_mask, [main_contour], -1, 1, thickness=3)

    wall_probe = cv2.dilate(wall_mask.astype(np.uint8), k3, iterations=3)
    gap_mask = perimeter_mask & (wall_probe == 0).astype(np.uint8)
    gap_mask = cv2.morphologyEx(gap_mask, cv2.MORPH_OPEN, k3, iterations=1)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(gap_mask, 8)
    openings: list[Opening] = []
    for i in range(1, num):
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        gap_px = float(max(bw, bh))
        if gap_px < _OPENING_MIN_GAP_PX or gap_px > _OPENING_MAX_GAP_PX:
            continue

        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])

        if m_per_px is not None:
            width_m: float | None = gap_px * m_per_px
            label = "Window" if width_m < _OPENING_DOOR_THRESHOLD_M else "Door"
        else:
            width_m = None
            label = "Opening"

        openings.append(Opening(x=x, y=y, w=bw, h=bh, width_m=width_m, label=label))
        if len(openings) >= _OPENING_MAX_COUNT:
            break

    return openings


# ---------------------------------------------------------------------------
# Scale estimation
# ---------------------------------------------------------------------------

def _estimate_scale_from_segments(segments: list[WallSegment]) -> float | None:
    """Estimate m_per_px from detected wall segment thicknesses.

    Uses the median thickness of structural-classified segments as
    the reference (assumed 150 mm RC wall in HDB plans).  Falls back
    to the 75th-percentile of all segments if no structural ones exist.
    """
    structural = [s.thickness_px for s in segments if s.wall_type == "structural"]
    if len(structural) >= 3:
        ref_px = float(np.median(structural))
    elif len(segments) >= 3:
        ref_px = float(np.percentile([s.thickness_px for s in segments], 75))
    else:
        return None
    if ref_px < 2.0:
        return None
    return 0.150 / ref_px


# ---------------------------------------------------------------------------
# HDB wall classification
# ---------------------------------------------------------------------------

def _snap_to_hdb(thickness_m: float) -> tuple[str, float]:
    """Map a detected wall thickness to HDB-standard type and snapped value."""
    if thickness_m < 0.070:
        return ("ferrolite", 0.044)
    if thickness_m < 0.125:
        return ("partition", 0.100)
    if thickness_m < 0.200:
        return ("structural", 0.150)
    return ("shelter", 0.300)


def _classify_wall_hdb(seg: WallSegment, m_per_px: float) -> WallSegment:
    """Return a new WallSegment enriched with real-world thickness and HDB type."""
    thickness_m = seg.thickness_px * m_per_px
    hdb_type, hdb_thickness_m = _snap_to_hdb(thickness_m)
    return WallSegment(
        x1=seg.x1, y1=seg.y1, x2=seg.x2, y2=seg.y2,
        thickness_px=seg.thickness_px,
        wall_type=seg.wall_type,
        thickness_m=thickness_m,
        hdb_type=hdb_type,
        hdb_thickness_m=hdb_thickness_m,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_floor_plan(img_rgb: np.ndarray) -> tuple[FloorPlanData, np.ndarray, np.ndarray]:
    """Extract structured floor plan data from a raster image.

    Returns:
        data:      FloorPlanData with classified walls, columns, openings
        wall_mask: binary wall mask (for debug/visualization)
        fill_mask: binary fill mask (for debug/visualization)
    """
    h, w = img_rgb.shape[:2]
    fill_mask = _build_fill_mask(img_rgb)
    dark = _extract_dark(img_rgb, fill_mask)

    walls, wall_mask = _extract_wall_segments(dark)
    m_per_px = _estimate_scale_from_segments(walls)
    columns = _detect_columns(img_rgb, fill_mask, wall_mask)
    openings = _detect_openings(wall_mask, m_per_px)

    if m_per_px is not None:
        walls = [_classify_wall_hdb(w, m_per_px) for w in walls]

    data = FloorPlanData(
        walls=walls,
        columns=columns,
        openings=openings,
        m_per_px=m_per_px,
        image_shape_hw=(h, w),
    )
    return data, wall_mask, fill_mask
