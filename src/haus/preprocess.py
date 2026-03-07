from __future__ import annotations
import cv2
import numpy as np

_DARK_THRESH = 150
_FILL_SAT_MIN = 35
_FILL_VAL_MIN = 60
_FILL_MIN_AREA = 500
_WALL_OPEN_LEN = 30
_EXTERIOR_DILATE = 51
_EXTERIOR_MAX_AREA = 5000
_SHELTER_WALL_RATIO = 0.70 # border darkness above this → household shelter
_PROT_MIN_AREA = 2000 # primary area threshold for protrusions
_PROT_DARK_AREA = 1000 # secondary: smaller protrusions with high dark content
_PROT_DARK_RATIO = 0.35 # secondary: internal dark pixel ratio threshold


def clean_floor_plan(img_rgb: np.ndarray) -> np.ndarray:
    """Remove door arcs, AC ledges, service yards, and exterior annotations."""
    img = img_rgb.copy()
    img = _erase_protrusions(img)
    img = _erase_door_arcs(img)
    img = _erase_exterior_marks(img)
    return img


def _build_fill_solid(img_rgb: np.ndarray) -> np.ndarray:
    """Build solidified fill mask from colored regions."""
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    sat = (
        (hsv[:, :, 1] > _FILL_SAT_MIN) & (hsv[:, :, 2] > _FILL_VAL_MIN)
    ).astype(np.uint8)
    sat = cv2.morphologyEx(sat, cv2.MORPH_CLOSE, np.ones((7, 1), np.uint8))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(sat, 8)
    fill = np.zeros_like(sat)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) >= _FILL_MIN_AREA:
            fill[labels == i] = 1
    solid = np.zeros_like(fill)
    num2, labels2, stats2, _ = cv2.connectedComponentsWithStats(fill, 8)
    for i in range(1, num2):
        if int(stats2[i, cv2.CC_STAT_AREA]) < 100:
            continue
        comp = (labels2 == i).astype(np.uint8)
        contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            cv2.drawContours(solid, [c], -1, 1, thickness=-1)
    return solid


def _build_wall_mask(dark: np.ndarray) -> np.ndarray:
    """Wall pixels: survive directional morphological opening."""
    k_h = np.ones((1, _WALL_OPEN_LEN), np.uint8)
    k_v = np.ones((_WALL_OPEN_LEN, 1), np.uint8)
    return cv2.bitwise_or(
        cv2.morphologyEx(dark, cv2.MORPH_OPEN, k_h),
        cv2.morphologyEx(dark, cv2.MORPH_OPEN, k_v),
    )


def _erase_door_arcs(img: np.ndarray) -> np.ndarray:
    """Erase quarter-circle door swing arcs.

    Phase 1: HoughCircles detects large arcs (even when connected to walls).
    Phase 2: Residual CC analysis catches smaller/isolated arcs.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    dark = (gray < _DARK_THRESH).astype(np.uint8) * 255
    walls = _build_wall_mask(dark)
    erase = np.zeros(img.shape[:2], dtype=np.uint8)
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    min_r = max(20, min(h, w) // 20)
    max_r = max(60, min(h, w) // 5)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.0,
        minDist=min_r * 3, param1=100, param2=50,
        minRadius=min_r, maxRadius=max_r,
    )
    if circles is not None:
        for cx, cy, r in circles[0]:
            cx, cy, r = int(cx), int(cy), int(r)
            ring = np.zeros_like(erase)
            cv2.circle(ring, (cx, cy), r, 1, max(4, int(r * 0.15)))
            arc_dark = (ring > 0) & (dark > 0) & (walls == 0)
            if np.count_nonzero(arc_dark) > 20:
                erase[arc_dark] = 1
    residual = cv2.bitwise_and(dark, cv2.bitwise_not(walls))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(residual, 8)
    for i in range(1, num):
        a = int(stats[i, cv2.CC_STAT_AREA])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        fr = a / max(bw * bh, 1)
        aspect = max(bw, bh) / max(min(bw, bh), 1)
        if fr < 0.20 and aspect < 2.5 and 50 < a < 15000 and min(bw, bh) > 12:
            erase[labels == i] = 1
    if np.count_nonzero(erase):
        erase = cv2.dilate(erase, np.ones((3, 3), np.uint8), iterations=1)
        img[erase > 0] = 255
    return img


def _is_shelter(comp: np.ndarray, dark: np.ndarray) -> bool:
    """Check if a protrusion component is a household shelter (thick dark walls)."""
    border = cv2.dilate(comp, np.ones((7, 7), np.uint8), iterations=2) - comp
    border_total = max(np.count_nonzero(border), 1)
    border_dark = np.count_nonzero((border > 0) & (dark > 0))
    return (border_dark / border_total) > _SHELTER_WALL_RATIO


def _dark_ratio(comp: np.ndarray, dark: np.ndarray) -> float:
    """Fraction of dark pixels inside a component mask."""
    area = max(np.count_nonzero(comp), 1)
    return np.count_nonzero((comp > 0) & (dark > 0)) / area


def _erase_protrusions(img: np.ndarray) -> np.ndarray:
    """Erase AC ledges and service yards using two-pass close+open.

    1. Close the fill mask to merge separated rooms into one body.
    2. Open at two scales (15% and 22% of short dim) to find protrusions.
    3. Filter: area > _PROT_MIN_AREA and wall_ratio < _SHELTER_WALL_RATIO.
    4. Dilate erase zone to cover walls/hatching inside the protrusion.
    """
    solid = _build_fill_solid(img)
    if np.count_nonzero(solid) < 1000:
        return img
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    dark = (gray < _DARK_THRESH).astype(np.uint8) * 255
    h, w = solid.shape
    short_dim = min(h, w)
    # close fill to merge rooms separated by walls
    k_close = np.ones((15, 15), np.uint8)
    merged = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, k_close, iterations=2)
    erase = np.zeros_like(solid)
    # two-pass: 15% catches smaller protrusions, 22% catches larger ones
    for frac in (0.15, 0.22):
        k_size = max(51, int(short_dim * frac)) | 1
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        opened = cv2.morphologyEx(merged, cv2.MORPH_OPEN, k)
        prot = ((merged > 0) & (opened == 0)).astype(np.uint8)
        if np.count_nonzero(prot) == 0:
            continue
        # close to merge fragmented protrusion components
        prot = cv2.morphologyEx(prot, cv2.MORPH_CLOSE,
                                np.ones((15, 15), np.uint8), iterations=1)
        num, labels, stats, _ = cv2.connectedComponentsWithStats(prot, 8)
        for i in range(1, num):
            area = int(stats[i, cv2.CC_STAT_AREA])
            comp = (labels == i).astype(np.uint8)
            if area < _PROT_DARK_AREA:
                continue
            if _is_shelter(comp, dark):
                continue
            if area >= _PROT_MIN_AREA or _dark_ratio(comp, dark) >= _PROT_DARK_RATIO:
                erase = cv2.bitwise_or(erase, comp)
    if np.count_nonzero(erase) == 0:
        return img
    # use bounding box + margin to fully cover AC ledge rooms
    num_e, labels_e, stats_e, _ = cv2.connectedComponentsWithStats(erase, 8)
    zone = np.zeros_like(erase)
    margin = max(15, short_dim // 30) # adaptive margin
    for i in range(1, num_e):
        x = max(0, int(stats_e[i, cv2.CC_STAT_LEFT]) - margin)
        y = max(0, int(stats_e[i, cv2.CC_STAT_TOP]) - margin)
        bw_e = int(stats_e[i, cv2.CC_STAT_WIDTH]) + 2 * margin
        bh_e = int(stats_e[i, cv2.CC_STAT_HEIGHT]) + 2 * margin
        zone[y:min(y + bh_e, h), x:min(x + bw_e, w)] = 1
    img[zone > 0] = 255
    return img


def _erase_exterior_marks(img: np.ndarray) -> np.ndarray:
    """Erase dark marks (text, arrows, dimension labels) outside the unit."""
    solid = _build_fill_solid(img)
    if np.count_nonzero(solid) < 1000:
        return img
    interior = cv2.dilate(
        solid, np.ones((_EXTERIOR_DILATE, _EXTERIOR_DILATE), np.uint8), iterations=1
    )
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    exterior_dark = ((gray < _DARK_THRESH) & (interior == 0)).astype(np.uint8)
    if np.count_nonzero(exterior_dark) == 0:
        return img
    num, labels, stats, _ = cv2.connectedComponentsWithStats(exterior_dark, 8)
    erase = np.zeros_like(exterior_dark)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) < _EXTERIOR_MAX_AREA:
            erase[labels == i] = 1
    if np.count_nonzero(erase):
        mask = cv2.dilate(erase, np.ones((3, 3), np.uint8), iterations=1)
        img[mask > 0] = 255
    return img
