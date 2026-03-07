from __future__ import annotations
import cv2
import numpy as np

_DARK_THRESH = 150
_FILL_SAT_MIN = 35
_FILL_VAL_MIN = 60
_FILL_MIN_AREA = 500
_WALL_OPEN_LEN = 20 # px — directional open kernel length
_ARC_MAX_FILL_RATIO = 0.15 # arcs at radius r, width t: fill = πt/2r ≈ 0.04-0.11
_ARC_MAX_ASPECT = 2.0 # arcs have ~square bbox
_ARC_MIN_AREA = 80
_ARC_MAX_AREA = 8000
_ARC_MIN_DIM = 20 # exclude text characters (typically < 20px)
_PROTRUSION_KERNEL_FRAC = 0.10 # fraction of unit short dim
_PROTRUSION_KERNEL_MIN = 25
_PROTRUSION_KERNEL_MAX = 100
_EXTERIOR_DILATE = 51 # px — generous interior zone margin
_EXTERIOR_MAX_AREA = 5000 # only erase small exterior marks


def clean_floor_plan(img_rgb: np.ndarray) -> np.ndarray:
    """Remove door arcs, AC ledges, laundry areas, and exterior annotations."""
    img = img_rgb.copy()
    img = _erase_door_arcs(img)
    img = _erase_protrusions(img)
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


def _erase_door_arcs(img: np.ndarray) -> np.ndarray:
    """Erase quarter-circle door swing arcs.

    Arcs are thin curved dark strokes that don't survive directional
    morphological opening (they're not long straight segments).  We find
    non-wall dark connected components whose bounding box is roughly square
    with a very low fill ratio — classic quarter-circle signature.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    dark = (gray < _DARK_THRESH).astype(np.uint8) * 255
    k_h = np.ones((1, _WALL_OPEN_LEN), np.uint8)
    k_v = np.ones((_WALL_OPEN_LEN, 1), np.uint8)
    walls = cv2.bitwise_or(
        cv2.morphologyEx(dark, cv2.MORPH_OPEN, k_h),
        cv2.morphologyEx(dark, cv2.MORPH_OPEN, k_v),
    )
    residual = cv2.bitwise_and(dark, cv2.bitwise_not(walls))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(residual, 8)
    erase = np.zeros(img.shape[:2], dtype=np.uint8)
    for i in range(1, num):
        a = int(stats[i, cv2.CC_STAT_AREA])
        w = int(stats[i, cv2.CC_STAT_WIDTH])
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        fill_ratio = a / max(w * h, 1)
        aspect = max(w, h) / max(min(w, h), 1)
        if (aspect < _ARC_MAX_ASPECT
                and fill_ratio < _ARC_MAX_FILL_RATIO
                and _ARC_MIN_AREA < a < _ARC_MAX_AREA
                and min(w, h) > _ARC_MIN_DIM):
            erase[labels == i] = 1
    if np.count_nonzero(erase):
        erase = cv2.dilate(erase, np.ones((3, 3), np.uint8), iterations=1)
        img[erase > 0] = 255
    return img


def _erase_protrusions(img: np.ndarray) -> np.ndarray:
    """Erase narrow exterior protrusions (AC ledges, laundry areas).

    Uses morphological opening on the solidified fill mask.  Protrusions
    narrower than ~10% of the unit's short dimension are removed.  Real
    rooms (bathrooms >= 1.5m, corridors >= 1.2m) survive because they
    exceed the kernel size.
    """
    solid = _build_fill_solid(img)
    if np.count_nonzero(solid) < 1000:
        return img
    coords = cv2.findNonZero(solid)
    if coords is None:
        return img
    _, _, bw, bh = cv2.boundingRect(coords)
    short_dim = min(bw, bh)
    k_size = int(short_dim * _PROTRUSION_KERNEL_FRAC)
    k_size = max(_PROTRUSION_KERNEL_MIN, min(_PROTRUSION_KERNEL_MAX, k_size))
    k_size = k_size | 1 # ensure odd
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
    opened = cv2.morphologyEx(solid, cv2.MORPH_OPEN, k)
    protrusions = ((solid > 0) & (opened == 0)).astype(np.uint8)
    if np.count_nonzero(protrusions) == 0:
        return img
    zone = cv2.dilate(protrusions, np.ones((5, 5), np.uint8), iterations=1)
    img[zone > 0] = 255
    return img


def _erase_exterior_marks(img: np.ndarray) -> np.ndarray:
    """Erase dark marks (text, arrows, dimension labels) outside the unit.

    Only erases small dark components that are clearly beyond a generous
    interior margin, so exterior walls are not affected.
    """
    solid = _build_fill_solid(img)
    if np.count_nonzero(solid) < 1000:
        return img
    interior = cv2.dilate(solid, np.ones((_EXTERIOR_DILATE, _EXTERIOR_DILATE), np.uint8), iterations=1)
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
