from __future__ import annotations
import cv2
import numpy as np

_DARK_THRESH = 150
_FILL_SAT_MIN = 35
_FILL_VAL_MIN = 60
_FILL_MIN_AREA = 500
_WALL_OPEN_LEN = 30
_EXTERIOR_DILATE = 51
_EXTERIOR_MAX_AREA = 10000
_SHELTER_WALL_RATIO = 0.70 # border darkness above this → household shelter
_PROT_MIN_AREA = 2000 # primary area threshold for protrusions
_PROT_DARK_AREA = 1000 # secondary: smaller protrusions with high dark content
_PROT_DARK_RATIO = 0.35 # secondary: internal dark pixel ratio threshold
_INPAINT_RADIUS = 5 # radius for Telea inpainting


def clean_floor_plan(img_rgb: np.ndarray) -> np.ndarray:
    """Remove door arcs, AC ledges, service yards, and exterior annotations."""
    img = img_rgb.copy()
    img = _erase_hatching(img)
    img = _erase_protrusions(img)
    img = _erase_door_arcs(img)
    img = _erase_exterior_marks(img)
    return img


def _inpaint_erase(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Erase masked pixels by inpainting from surrounding colors."""
    if np.count_nonzero(mask) == 0:
        return img
    mask_u8 = (mask > 0).astype(np.uint8) * 255
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    result = cv2.inpaint(bgr, mask_u8, _INPAINT_RADIUS, cv2.INPAINT_TELEA)
    return cv2.cvtColor(result, cv2.COLOR_BGR2RGB)


def _build_fill_solid(img_rgb: np.ndarray) -> np.ndarray:
    """Build solidified fill mask from colored regions."""
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    sat = (
        (hsv[:, :, 1] > _FILL_SAT_MIN) & (hsv[:, :, 2] > _FILL_VAL_MIN)
    ).astype(np.uint8)
    sat = cv2.morphologyEx(sat, cv2.MORPH_CLOSE, np.ones((7, 1), np.uint8))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(sat, connectivity=8)
    fill = np.zeros_like(sat)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) >= _FILL_MIN_AREA:
            fill[labels == i] = 1
    solid = np.zeros_like(fill)
    num2, labels2, stats2, _ = cv2.connectedComponentsWithStats(fill, connectivity=8)
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
    """Erase quarter-circle door swing arcs (solid and dashed).

    Phase 1: HoughCircles on original + closed image. Only erases pixels
             from CCs whose majority lies on the detected ring (prevents
             erasing text characters that happen to intersect a ring).
    Phase 2: Residual CC analysis catches isolated arc fragments.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    dark = (gray < _DARK_THRESH).astype(np.uint8) * 255
    walls = _build_wall_mask(dark)
    h, w = gray.shape
    min_r = max(20, min(h, w) // 20)
    max_r = max(60, min(h, w) // 5)

    # precompute residual CCs (non-wall dark) for per-CC ring validation
    residual = cv2.bitwise_and(dark, cv2.bitwise_not(walls))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(residual, connectivity=8)
    # cache CC areas
    cc_areas = np.zeros(num, dtype=np.int32)
    for i in range(1, num):
        cc_areas[i] = int(stats[i, cv2.CC_STAT_AREA])

    erase = np.zeros((h, w), dtype=np.uint8)

    def _detect_hough_arcs(src_gray):
        blurred = cv2.GaussianBlur(src_gray, (9, 9), 2)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, dp=1.0,
            minDist=min_r * 3, param1=100, param2=40,
            minRadius=min_r, maxRadius=max_r,
        )
        if circles is None:
            return
        for cx, cy, r in circles[0]:
            cx, cy, r = int(cx), int(cy), int(r)
            ring = np.zeros_like(erase)
            cv2.circle(ring, (cx, cy), r, 1, max(4, int(r * 0.15)))
            ring_mask = (ring > 0) & (dark > 0) & (walls == 0)
            if np.count_nonzero(ring_mask) < 20:
                continue
            # per-CC validation: only erase CCs where >40% of their pixels
            # lie on the ring (true arc segments). skip text CCs that just
            # happen to intersect the ring.
            ring_labels = labels[ring_mask]
            hit_ids = set(ring_labels) - {0}
            for cc_id in hit_ids:
                total = cc_areas[cc_id]
                if total < 5:
                    continue
                on_ring = np.count_nonzero(ring_labels == cc_id)
                if on_ring / total > 0.4:
                    erase[(labels == cc_id) & (dark > 0) & (walls == 0)] = 1

    # phase 1a: solid arcs
    _detect_hough_arcs(gray)
    # phase 1b: close small gaps to connect dashed arcs, then detect
    dark_closed = cv2.morphologyEx(dark, cv2.MORPH_CLOSE,
                                   np.ones((5, 5), np.uint8), iterations=2)
    gray_closed = gray.copy()
    gray_closed[dark_closed > 0] = 0
    _detect_hough_arcs(gray_closed)

    # phase 2: residual non-wall dark CCs that look like arcs
    for i in range(1, num):
        a = int(stats[i, cv2.CC_STAT_AREA])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        fr = a / max(bw * bh, 1)
        aspect = max(bw, bh) / max(min(bw, bh), 1)
        # arcs: low fill ratio, near-square bbox, reasonable size
        if fr < 0.18 and aspect < 2.0 and 80 < a < 15000 and min(bw, bh) > 15:
            erase[labels == i] = 1

    if np.count_nonzero(erase):
        erase = cv2.dilate(erase, np.ones((3, 3), np.uint8), iterations=1)
        img = _inpaint_erase(img, erase)
    return img


def _is_shelter(comp: np.ndarray, dark: np.ndarray) -> bool:
    """Check if a protrusion component is a household shelter (thick dark walls)."""
    border = cv2.dilate(comp, np.ones((7, 7), np.uint8), iterations=2) - comp
    border_total = max(np.count_nonzero(border), 1)
    border_dark = np.count_nonzero((border > 0) & (dark > 0))
    return bool((border_dark / border_total) > _SHELTER_WALL_RATIO)


def _dark_ratio(comp: np.ndarray, dark: np.ndarray) -> float:
    """Fraction of dark pixels inside a component mask."""
    area = max(np.count_nonzero(comp), 1)
    return np.count_nonzero((comp > 0) & (dark > 0)) / area


def _detect_hatching(img_rgb: np.ndarray) -> np.ndarray:
    """Detect vertical hatching regions (AC ledge indicator)."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    dark = (gray < _DARK_THRESH).astype(np.uint8) * 255
    vert = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                            np.ones((_WALL_OPEN_LEN, 1), np.uint8))
    if np.count_nonzero(vert) < 50:
        return np.zeros(gray.shape, dtype=np.uint8)
    thick = cv2.morphologyEx(vert, cv2.MORPH_OPEN, np.ones((1, 8), np.uint8))
    thin = ((vert > 0) & (thick == 0)).astype(np.uint8)
    if np.count_nonzero(thin) < 30:
        return np.zeros(gray.shape, dtype=np.uint8)
    density = cv2.blur(thin.astype(np.float32), (25, 5))
    hatch_raw = (density > 0.25).astype(np.uint8)
    hatch_raw = cv2.morphologyEx(hatch_raw, cv2.MORPH_CLOSE,
                                 np.ones((5, 5), np.uint8))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(hatch_raw, connectivity=8)
    h, w = gray.shape
    max_dim = max(100, min(h, w) // 3)
    hatch = np.zeros(gray.shape, dtype=np.uint8)
    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if area > 200 and bw > 10 and bh > 10 and max(bw, bh) < max_dim:
            hatch[labels == i] = 1
    return hatch


def _erase_hatching(img: np.ndarray) -> np.ndarray:
    """Erase AC ledge rooms identified by hatching at the floor plan boundary."""
    hatching = _detect_hatching(img)
    if np.count_nonzero(hatching) == 0:
        return img
    solid = _build_fill_solid(img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    dark = (gray < _DARK_THRESH).astype(np.uint8) * 255
    h, w = img.shape[:2]
    num, labels, stats, _ = cv2.connectedComponentsWithStats(hatching, connectivity=8)
    erase = np.zeros(img.shape[:2], dtype=np.uint8)
    for i in range(1, num):
        comp = (labels == i).astype(np.uint8)
        hatch_area = np.count_nonzero(comp)
        fill_overlap = np.count_nonzero((comp > 0) & (solid > 0))
        fill_ratio = fill_overlap / max(hatch_area, 1)
        if fill_ratio < 0.35: # boundary hatching (AC ledge)
            ys, xs = np.where(comp > 0)
            seed = (int(xs.mean()), int(ys.mean()))
            v_walls = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                                       np.ones((_WALL_OPEN_LEN, 1), np.uint8))
            h_walls = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                                       np.ones((1, _WALL_OPEN_LEN), np.uint8))
            barrier = cv2.bitwise_or(v_walls, h_walls)
            vert_only = ((v_walls > 0) & (h_walls == 0)).astype(np.uint8)
            comp_exp = cv2.dilate(comp, np.ones((3, 15), np.uint8), iterations=2)
            barrier[(comp_exp > 0) & (vert_only > 0)] = 0
            # thicken barrier to close small gaps that cause flood leaks
            barrier = cv2.dilate(barrier, np.ones((5, 5), np.uint8), iterations=1)
            flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
            fill_img = barrier.copy()
            cv2.floodFill(fill_img, flood_mask, seed, 128)
            room = (flood_mask[1:-1, 1:-1] > 0).astype(np.uint8)
            room_area = np.count_nonzero(room)
            # max room: scale with hatching size but cap at 15% of image
            max_room = min(hatch_area * 20, int(h * w * 0.15))
            if 100 < room_area < max_room:
                room_dilated = cv2.dilate(room, np.ones((7, 7), np.uint8), iterations=2)
                erase = cv2.bitwise_or(erase, room_dilated)
    if np.count_nonzero(erase):
        img[erase > 0] = 255
    return img


def _erase_protrusions(img: np.ndarray) -> np.ndarray:
    """Erase AC ledges and service yards using two-pass close+open."""
    solid = _build_fill_solid(img)
    if np.count_nonzero(solid) < 1000:
        return img
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    dark = (gray < _DARK_THRESH).astype(np.uint8) * 255
    h, w = solid.shape
    short_dim = min(h, w)
    k_close = np.ones((15, 15), np.uint8)
    merged = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, k_close, iterations=2)
    erase = np.zeros_like(solid)
    for frac in (0.15, 0.22):
        k_size = max(51, int(short_dim * frac)) | 1
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        opened = cv2.morphologyEx(merged, cv2.MORPH_OPEN, k)
        prot = ((merged > 0) & (opened == 0)).astype(np.uint8)
        if np.count_nonzero(prot) == 0:
            continue
        prot = cv2.morphologyEx(prot, cv2.MORPH_CLOSE,
                                np.ones((15, 15), np.uint8), iterations=1)
        num, labels, stats, _ = cv2.connectedComponentsWithStats(prot, connectivity=8)
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
    num_e, labels_e, stats_e, _ = cv2.connectedComponentsWithStats(erase, connectivity=8)
    zone = np.zeros_like(erase)
    for i in range(1, num_e):
        cw = int(stats_e[i, cv2.CC_STAT_WIDTH])
        ch = int(stats_e[i, cv2.CC_STAT_HEIGHT])
        margin = min(max(20, cw // 3, ch // 3), 45)
        x = max(0, int(stats_e[i, cv2.CC_STAT_LEFT]) - margin)
        y = max(0, int(stats_e[i, cv2.CC_STAT_TOP]) - margin)
        bw_e = cw + 2 * margin
        bh_e = ch + 2 * margin
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
    num, labels, stats, _ = cv2.connectedComponentsWithStats(exterior_dark, connectivity=8)
    erase = np.zeros_like(exterior_dark)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) < _EXTERIOR_MAX_AREA:
            erase[labels == i] = 1
    if np.count_nonzero(erase):
        mask = cv2.dilate(erase, np.ones((3, 3), np.uint8), iterations=1)
        img[mask > 0] = 255
    return img
