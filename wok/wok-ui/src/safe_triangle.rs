//! Pointer-intent ("safe triangle") helper.
//!
//! When a user hovers a parent menu item that has a submenu, naive hover
//! routing dismisses the submenu the moment the cursor leaves the parent's
//! rect — even if the cursor is on its way *to* the submenu. The safe-triangle
//! technique resolves this: while the cursor stays inside the triangle whose
//! apex is the cursor's previous position and whose base is the submenu's
//! near edge, the parent stays "active" and the submenu stays open.
//!
//! Pure 2-D geometry; no UI dependency.

/// Axis-aligned rectangle in pixels.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Rect {
    /// Top-left x.
    pub x: f64,
    /// Top-left y.
    pub y: f64,
    /// Width in pixels (≥0).
    pub w: f64,
    /// Height in pixels (≥0).
    pub h: f64,
}

impl Rect {
    /// Right edge x.
    pub fn right(&self) -> f64 {
        self.x + self.w
    }
    /// Bottom edge y.
    pub fn bottom(&self) -> f64 {
        self.y + self.h
    }
}

/// Side of `target` that the cursor approached from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Side {
    /// Cursor approached from the left of `target`.
    Left,
    /// Cursor approached from the right of `target`.
    Right,
    /// Cursor approached from above `target`.
    Top,
    /// Cursor approached from below `target`.
    Bottom,
}

/// Decide whether `cursor` is "still on the way" to `target` given that the
/// pointer was at `apex` a moment ago. Returns `true` if the cursor is inside
/// the triangle with apex at `apex` and base on the side of `target` nearest
/// to `apex`. Returns `false` if the cursor is inside `target` itself
/// (caller should treat that as "arrived"), or has strayed outside the
/// triangle (caller should dismiss).
///
/// Algorithm:
/// 1. Determine which side of `target` `apex` is on (closest face).
/// 2. Form a triangle (apex, near-corner-A, near-corner-B).
/// 3. Test point-in-triangle via barycentric signs.
pub fn intent_preserved(apex: (f64, f64), cursor: (f64, f64), target: Rect) -> bool {
    if point_in_rect(cursor, target) {
        return false;
    }
    let side = approach_side(apex, target);
    let (a, b) = base_corners(target, side);
    point_in_triangle(cursor, apex, a, b)
}

/// Side of `target` that `apex` is on (used internally; exposed for tests).
pub fn approach_side(apex: (f64, f64), target: Rect) -> Side {
    let (px, py) = apex;
    let dx_left = target.x - px;
    let dx_right = px - target.right();
    let dy_top = target.y - py;
    let dy_bot = py - target.bottom();
    let candidates = [
        (Side::Left, dx_left),
        (Side::Right, dx_right),
        (Side::Top, dy_top),
        (Side::Bottom, dy_bot),
    ];
    candidates
        .into_iter()
        .filter(|(_, v)| *v >= 0.0)
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
        .map(|(s, _)| s)
        // apex inside the rect — pick a deterministic default; caller already
        // checks `point_in_rect(cursor, target)` so this branch is rare.
        .unwrap_or(Side::Left)
}

fn base_corners(t: Rect, side: Side) -> ((f64, f64), (f64, f64)) {
    match side {
        Side::Left => ((t.x, t.y), (t.x, t.bottom())),
        Side::Right => ((t.right(), t.y), (t.right(), t.bottom())),
        Side::Top => ((t.x, t.y), (t.right(), t.y)),
        Side::Bottom => ((t.x, t.bottom()), (t.right(), t.bottom())),
    }
}

fn point_in_rect(p: (f64, f64), r: Rect) -> bool {
    p.0 >= r.x && p.0 <= r.right() && p.1 >= r.y && p.1 <= r.bottom()
}

fn point_in_triangle(p: (f64, f64), a: (f64, f64), b: (f64, f64), c: (f64, f64)) -> bool {
    let d1 = sign(p, a, b);
    let d2 = sign(p, b, c);
    let d3 = sign(p, c, a);
    let neg = (d1 < 0.0) || (d2 < 0.0) || (d3 < 0.0);
    let pos = (d1 > 0.0) || (d2 > 0.0) || (d3 > 0.0);
    !(neg && pos)
}

fn sign(p1: (f64, f64), p2: (f64, f64), p3: (f64, f64)) -> f64 {
    (p1.0 - p3.0) * (p2.1 - p3.1) - (p2.0 - p3.0) * (p1.1 - p3.1)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rect(x: f64, y: f64, w: f64, h: f64) -> Rect {
        Rect { x, y, w, h }
    }

    #[test]
    fn cursor_inside_target_means_arrived() {
        // arrived → not "still preserving intent".
        let r = rect(100.0, 100.0, 50.0, 50.0);
        assert!(!intent_preserved((0.0, 0.0), (110.0, 110.0), r));
    }

    #[test]
    fn straight_path_to_target_preserves_intent() {
        let r = rect(100.0, 100.0, 50.0, 50.0);
        // apex left of target; cursor moving right along centre line.
        assert!(intent_preserved((0.0, 125.0), (50.0, 125.0), r));
        assert!(intent_preserved((0.0, 125.0), (90.0, 125.0), r));
    }

    #[test]
    fn divergent_path_breaks_intent() {
        let r = rect(100.0, 100.0, 50.0, 50.0);
        // cursor moved sharply away on Y while X barely advanced.
        assert!(!intent_preserved((0.0, 125.0), (10.0, 0.0), r));
        assert!(!intent_preserved((0.0, 125.0), (10.0, 400.0), r));
    }

    #[test]
    fn approach_side_picks_dominant_axis() {
        let r = rect(100.0, 100.0, 50.0, 50.0);
        assert_eq!(approach_side((0.0, 125.0), r), Side::Left);
        assert_eq!(approach_side((300.0, 125.0), r), Side::Right);
        assert_eq!(approach_side((125.0, 0.0), r), Side::Top);
        assert_eq!(approach_side((125.0, 300.0), r), Side::Bottom);
    }

    #[test]
    fn approach_from_below_path_works() {
        let r = rect(100.0, 100.0, 50.0, 50.0);
        // apex below target, cursor moving up
        assert!(intent_preserved((125.0, 300.0), (125.0, 200.0), r));
        // diverged sideways
        assert!(!intent_preserved((125.0, 300.0), (400.0, 200.0), r));
    }

    #[test]
    fn boundary_is_inclusive() {
        let r = rect(100.0, 100.0, 50.0, 50.0);
        // cursor exactly on near edge → counted as inside-rect ("arrived").
        assert!(!intent_preserved((0.0, 125.0), (100.0, 125.0), r));
    }

    #[test]
    fn point_in_triangle_basic() {
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let c = (5.0, 10.0);
        assert!(point_in_triangle((5.0, 5.0), a, b, c));
        assert!(!point_in_triangle((20.0, 5.0), a, b, c));
    }
}
