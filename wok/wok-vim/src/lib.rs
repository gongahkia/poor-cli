//! Wok vim — pure state machine for vim-style editor input.
//!
//! Inputs: a stream of [`Stroke`]s (parsed by the caller). Outputs: zero or
//! more [`Edit`] operations (deltas the caller applies to its buffer).
//!
//! Scope (MVP framework):
//!   - Modes: Normal, Insert, Visual, VisualLine, OpPending.
//!   - Operators: `d`, `c`, `y`.
//!   - Motions: `h j k l 0 $ w b e f<c> F<c> t<c> T<c>`.
//!   - Counts: `[0-9]+` prefix.
//!   - Registers: `"<a..z>` prefix.
//!   - Verbs: `i I a A o O x p P u` insert/append/yank/paste/undo.
//!
//! Out of scope (deferred to follow-ups): text objects, `.` repeat, marks,
//! search-as-motion, ex commands, macros, scrolloff math.
//!
//! No I/O. No allocation beyond the returned `Vec<Edit>`.

#![deny(missing_docs)]
#![forbid(unsafe_code)]

/// Input stroke. The caller's keymap layer normalises raw keys into this.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stroke {
    /// A printable character (letters, digits, punctuation).
    Char(char),
    /// `<Esc>` — exit current mode.
    Esc,
    /// `<CR>` — submit / newline.
    Enter,
    /// `<BS>` — delete backwards.
    Backspace,
}

/// Editor mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    /// Normal mode (motions and operators).
    Normal,
    /// Insert mode (text typed verbatim).
    Insert,
    /// Character-wise visual selection.
    Visual,
    /// Line-wise visual selection.
    VisualLine,
    /// Operator-pending: after `d`/`c`/`y`, awaiting a motion.
    OpPending,
}

/// An operator (deletion, change, yank).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Operator {
    /// Delete.
    Delete,
    /// Change (delete + enter Insert).
    Change,
    /// Yank.
    Yank,
}

/// A motion that resolves to a (start, end) byte range relative to the cursor.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Motion {
    /// `h` — one cell left.
    Left,
    /// `l` — one cell right.
    Right,
    /// `j` — one row down.
    Down,
    /// `k` — one row up.
    Up,
    /// `0` — line start.
    LineStart,
    /// `$` — line end.
    LineEnd,
    /// `w` — next word start.
    WordForward,
    /// `b` — previous word start.
    WordBackward,
    /// `e` — current/next word end.
    WordEnd,
    /// `f<c>` — to char `c` forward (inclusive).
    FindForward(char),
    /// `F<c>` — to char `c` backward (inclusive).
    FindBackward(char),
    /// `t<c>` — to one before char `c` forward.
    TillForward(char),
    /// `T<c>` — to one after char `c` backward.
    TillBackward(char),
}

/// Pending state for multi-key sequences.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Pending {
    /// Awaiting target char for `f`.
    FindForward,
    /// Awaiting target char for `F`.
    FindBackward,
    /// Awaiting target char for `t`.
    TillForward,
    /// Awaiting target char for `T`.
    TillBackward,
    /// Awaiting register name after `"`.
    Register,
}

/// Edit operation emitted by the state machine.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Edit {
    /// Apply `motion` `count` times (caller resolves to range).
    ApplyMotion {
        /// Motion to apply.
        motion: Motion,
        /// Repeat count (≥1).
        count: usize,
    },
    /// Apply `operator` over a motion `count` times. Resolved to a range by
    /// the caller, who then deletes/changes/yanks.
    ApplyOperator {
        /// Operator.
        operator: Operator,
        /// Motion describing the affected range.
        motion: Motion,
        /// Repeat count for the motion (≥1).
        count: usize,
        /// Active register, if any.
        register: Option<char>,
    },
    /// Linewise operator (e.g. `dd`, `yy`). `count` lines starting at cursor.
    ApplyLinewise {
        /// Operator.
        operator: Operator,
        /// Number of lines (≥1).
        count: usize,
        /// Active register, if any.
        register: Option<char>,
    },
    /// Insert literal text at cursor (issued in Insert mode).
    InsertChar(char),
    /// Delete one char to the left of cursor (Backspace in Insert).
    BackspaceChar,
    /// Insert a newline.
    InsertNewline,
    /// `o` — open a new line below and enter Insert.
    OpenLineBelow,
    /// `O` — open a new line above and enter Insert.
    OpenLineAbove,
    /// `x` — delete char under cursor `count` times.
    DeleteCharUnderCursor {
        /// Repeat count.
        count: usize,
    },
    /// `p` — paste from register after cursor.
    PasteAfter {
        /// Active register, if any.
        register: Option<char>,
    },
    /// `P` — paste from register before cursor.
    PasteBefore {
        /// Active register, if any.
        register: Option<char>,
    },
    /// `u` — undo last change.
    Undo,
    /// Mode transition signal (caller may toggle UI cues).
    EnterMode(Mode),
}

/// Vim state machine. Holds pending operator/count/register/sub-state.
#[derive(Debug, Clone)]
pub struct Vim {
    mode: Mode,
    count: usize,
    operator: Option<Operator>,
    /// Operator originally requested by the user — used to detect linewise
    /// duplicates like `dd`/`cc`/`yy`.
    operator_key: Option<char>,
    register: Option<char>,
    pending: Option<Pending>,
}

impl Default for Vim {
    fn default() -> Self {
        Self::new()
    }
}

impl Vim {
    /// New machine in Normal mode.
    pub const fn new() -> Self {
        Self {
            mode: Mode::Normal,
            count: 0,
            operator: None,
            operator_key: None,
            register: None,
            pending: None,
        }
    }

    /// Active mode.
    pub const fn mode(&self) -> Mode {
        self.mode
    }

    /// Active count (0 if none staged).
    pub const fn count(&self) -> usize {
        self.count
    }

    /// Active register, if staged.
    pub const fn register(&self) -> Option<char> {
        self.register
    }

    /// Step the machine by one stroke. Returns 0+ edits to apply.
    pub fn on_stroke(&mut self, stroke: Stroke) -> Vec<Edit> {
        match self.mode {
            Mode::Insert => self.step_insert(stroke),
            Mode::Normal | Mode::OpPending => self.step_normal_or_op(stroke),
            Mode::Visual | Mode::VisualLine => self.step_visual(stroke),
        }
    }

    fn step_insert(&mut self, stroke: Stroke) -> Vec<Edit> {
        match stroke {
            Stroke::Esc => {
                self.mode = Mode::Normal;
                vec![Edit::EnterMode(Mode::Normal)]
            }
            Stroke::Enter => vec![Edit::InsertNewline],
            Stroke::Backspace => vec![Edit::BackspaceChar],
            Stroke::Char(c) => vec![Edit::InsertChar(c)],
        }
    }

    fn step_visual(&mut self, stroke: Stroke) -> Vec<Edit> {
        match stroke {
            Stroke::Esc => {
                self.mode = Mode::Normal;
                vec![Edit::EnterMode(Mode::Normal)]
            }
            // visual mode operator selection collapses to ApplyOperator over
            // an implicit "selection" motion (caller-tracked); MVP returns
            // EnterMode + a placeholder so callers wire selection ranges.
            Stroke::Char('d') | Stroke::Char('c') | Stroke::Char('y') => {
                let op = match stroke {
                    Stroke::Char('d') => Operator::Delete,
                    Stroke::Char('c') => Operator::Change,
                    _ => Operator::Yank,
                };
                let next_mode = if matches!(op, Operator::Change) {
                    Mode::Insert
                } else {
                    Mode::Normal
                };
                self.mode = next_mode;
                vec![
                    Edit::ApplyLinewise {
                        operator: op,
                        count: 1,
                        register: self.take_register(),
                    },
                    Edit::EnterMode(next_mode),
                ]
            }
            _ => Vec::new(),
        }
    }

    fn step_normal_or_op(&mut self, stroke: Stroke) -> Vec<Edit> {
        // resolve pending sub-states first.
        if let Some(pending) = self.pending {
            return self.resolve_pending(pending, stroke);
        }
        match stroke {
            Stroke::Esc => {
                self.reset_pending();
                self.mode = Mode::Normal;
                Vec::new()
            }
            Stroke::Enter | Stroke::Backspace => Vec::new(),
            Stroke::Char(c) => self.step_normal_char(c),
        }
    }

    fn step_normal_char(&mut self, c: char) -> Vec<Edit> {
        // count digits (but '0' as first digit is a motion to line start).
        if c.is_ascii_digit() && !(c == '0' && self.count == 0) {
            let d = c.to_digit(10).unwrap_or(0) as usize;
            self.count = self.count.saturating_mul(10).saturating_add(d);
            return Vec::new();
        }

        match c {
            '"' => {
                self.pending = Some(Pending::Register);
                Vec::new()
            }
            'd' | 'c' | 'y' => self.handle_operator_key(c),
            'i' => {
                self.mode = Mode::Insert;
                vec![Edit::EnterMode(Mode::Insert)]
            }
            'I' => {
                self.mode = Mode::Insert;
                vec![
                    Edit::ApplyMotion {
                        motion: Motion::LineStart,
                        count: 1,
                    },
                    Edit::EnterMode(Mode::Insert),
                ]
            }
            'a' => {
                self.mode = Mode::Insert;
                vec![
                    Edit::ApplyMotion {
                        motion: Motion::Right,
                        count: 1,
                    },
                    Edit::EnterMode(Mode::Insert),
                ]
            }
            'A' => {
                self.mode = Mode::Insert;
                vec![
                    Edit::ApplyMotion {
                        motion: Motion::LineEnd,
                        count: 1,
                    },
                    Edit::EnterMode(Mode::Insert),
                ]
            }
            'o' => {
                self.mode = Mode::Insert;
                vec![Edit::OpenLineBelow, Edit::EnterMode(Mode::Insert)]
            }
            'O' => {
                self.mode = Mode::Insert;
                vec![Edit::OpenLineAbove, Edit::EnterMode(Mode::Insert)]
            }
            'x' => {
                let n = self.take_count();
                vec![Edit::DeleteCharUnderCursor { count: n }]
            }
            'p' => {
                let r = self.take_register();
                vec![Edit::PasteAfter { register: r }]
            }
            'P' => {
                let r = self.take_register();
                vec![Edit::PasteBefore { register: r }]
            }
            'u' => vec![Edit::Undo],
            'v' => {
                self.mode = Mode::Visual;
                vec![Edit::EnterMode(Mode::Visual)]
            }
            'V' => {
                self.mode = Mode::VisualLine;
                vec![Edit::EnterMode(Mode::VisualLine)]
            }
            'f' => {
                self.pending = Some(Pending::FindForward);
                Vec::new()
            }
            'F' => {
                self.pending = Some(Pending::FindBackward);
                Vec::new()
            }
            't' => {
                self.pending = Some(Pending::TillForward);
                Vec::new()
            }
            'T' => {
                self.pending = Some(Pending::TillBackward);
                Vec::new()
            }
            // motions
            'h' => self.emit_motion(Motion::Left),
            'l' => self.emit_motion(Motion::Right),
            'j' => self.emit_motion(Motion::Down),
            'k' => self.emit_motion(Motion::Up),
            '0' => self.emit_motion(Motion::LineStart),
            '$' => self.emit_motion(Motion::LineEnd),
            'w' => self.emit_motion(Motion::WordForward),
            'b' => self.emit_motion(Motion::WordBackward),
            'e' => self.emit_motion(Motion::WordEnd),
            _ => {
                // unknown key — drop pending state to avoid wedging.
                self.reset_pending();
                if self.mode == Mode::OpPending {
                    self.mode = Mode::Normal;
                }
                Vec::new()
            }
        }
    }

    fn handle_operator_key(&mut self, key: char) -> Vec<Edit> {
        let op = match key {
            'd' => Operator::Delete,
            'c' => Operator::Change,
            _ => Operator::Yank,
        };

        // dd / cc / yy → linewise.
        if self.operator_key == Some(key) && self.mode == Mode::OpPending {
            let n = self.take_count();
            let r = self.take_register();
            self.operator = None;
            self.operator_key = None;
            self.mode = if matches!(op, Operator::Change) {
                Mode::Insert
            } else {
                Mode::Normal
            };
            let mut out = vec![Edit::ApplyLinewise {
                operator: op,
                count: n,
                register: r,
            }];
            if matches!(op, Operator::Change) {
                out.push(Edit::EnterMode(Mode::Insert));
            }
            return out;
        }

        // first time: enter operator-pending and stage operator.
        self.operator = Some(op);
        self.operator_key = Some(key);
        self.mode = Mode::OpPending;
        Vec::new()
    }

    fn emit_motion(&mut self, motion: Motion) -> Vec<Edit> {
        let n = self.take_count();
        if let Some(operator) = self.operator.take() {
            self.operator_key = None;
            let r = self.take_register();
            let next_mode = if matches!(operator, Operator::Change) {
                Mode::Insert
            } else {
                Mode::Normal
            };
            self.mode = next_mode;
            let mut out = vec![Edit::ApplyOperator {
                operator,
                motion,
                count: n,
                register: r,
            }];
            if matches!(operator, Operator::Change) {
                out.push(Edit::EnterMode(Mode::Insert));
            }
            out
        } else {
            vec![Edit::ApplyMotion { motion, count: n }]
        }
    }

    fn resolve_pending(&mut self, pending: Pending, stroke: Stroke) -> Vec<Edit> {
        self.pending = None;
        match (pending, stroke) {
            (Pending::Register, Stroke::Char(c)) if c.is_ascii_alphabetic() => {
                self.register = Some(c.to_ascii_lowercase());
                Vec::new()
            }
            (Pending::FindForward, Stroke::Char(c)) => self.emit_motion(Motion::FindForward(c)),
            (Pending::FindBackward, Stroke::Char(c)) => self.emit_motion(Motion::FindBackward(c)),
            (Pending::TillForward, Stroke::Char(c)) => self.emit_motion(Motion::TillForward(c)),
            (Pending::TillBackward, Stroke::Char(c)) => self.emit_motion(Motion::TillBackward(c)),
            _ => {
                // bail; reset count + operator so future strokes work.
                self.count = 0;
                self.operator = None;
                self.operator_key = None;
                if self.mode == Mode::OpPending {
                    self.mode = Mode::Normal;
                }
                Vec::new()
            }
        }
    }

    fn reset_pending(&mut self) {
        self.pending = None;
        self.count = 0;
        self.operator = None;
        self.operator_key = None;
        self.register = None;
    }

    fn take_count(&mut self) -> usize {
        let n = self.count.max(1);
        self.count = 0;
        n
    }

    fn take_register(&mut self) -> Option<char> {
        self.register.take()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(seq: &str) -> (Vim, Vec<Edit>) {
        let mut v = Vim::new();
        let mut edits = Vec::new();
        for c in seq.chars() {
            edits.extend(v.on_stroke(Stroke::Char(c)));
        }
        (v, edits)
    }

    #[test]
    fn motions_emit_apply_motion() {
        let (_, edits) = run("h");
        assert_eq!(
            edits,
            vec![Edit::ApplyMotion {
                motion: Motion::Left,
                count: 1
            }]
        );
    }

    #[test]
    fn count_prefix_scales_motion() {
        let (_, edits) = run("3w");
        assert_eq!(
            edits,
            vec![Edit::ApplyMotion {
                motion: Motion::WordForward,
                count: 3
            }]
        );
    }

    #[test]
    fn multi_digit_count() {
        let (_, edits) = run("42j");
        assert_eq!(
            edits,
            vec![Edit::ApplyMotion {
                motion: Motion::Down,
                count: 42
            }]
        );
    }

    #[test]
    fn zero_alone_is_line_start_motion() {
        let (_, edits) = run("0");
        assert_eq!(
            edits,
            vec![Edit::ApplyMotion {
                motion: Motion::LineStart,
                count: 1
            }]
        );
    }

    #[test]
    fn dollar_is_line_end_motion() {
        let (_, edits) = run("$");
        assert_eq!(
            edits,
            vec![Edit::ApplyMotion {
                motion: Motion::LineEnd,
                count: 1
            }]
        );
    }

    #[test]
    fn operator_motion_emits_apply_operator() {
        let (vim, edits) = run("dw");
        assert_eq!(
            edits,
            vec![Edit::ApplyOperator {
                operator: Operator::Delete,
                motion: Motion::WordForward,
                count: 1,
                register: None,
            }]
        );
        assert_eq!(vim.mode(), Mode::Normal);
    }

    #[test]
    fn change_motion_enters_insert_mode() {
        let (vim, edits) = run("cw");
        assert_eq!(edits.len(), 2);
        assert!(matches!(edits[0], Edit::ApplyOperator { .. }));
        assert!(matches!(edits[1], Edit::EnterMode(Mode::Insert)));
        assert_eq!(vim.mode(), Mode::Insert);
    }

    #[test]
    fn dd_is_linewise_delete() {
        let (_, edits) = run("dd");
        assert_eq!(
            edits,
            vec![Edit::ApplyLinewise {
                operator: Operator::Delete,
                count: 1,
                register: None
            }]
        );
    }

    #[test]
    fn three_dd_is_linewise_three() {
        let (_, edits) = run("3dd");
        assert_eq!(
            edits,
            vec![Edit::ApplyLinewise {
                operator: Operator::Delete,
                count: 3,
                register: None
            }]
        );
    }

    #[test]
    fn count_with_operator_motion() {
        let (_, edits) = run("2dw");
        assert_eq!(
            edits,
            vec![Edit::ApplyOperator {
                operator: Operator::Delete,
                motion: Motion::WordForward,
                count: 2,
                register: None
            }]
        );
    }

    #[test]
    fn register_then_yank_motion() {
        let (_, edits) = run("\"ayw");
        assert_eq!(
            edits,
            vec![Edit::ApplyOperator {
                operator: Operator::Yank,
                motion: Motion::WordForward,
                count: 1,
                register: Some('a'),
            }]
        );
    }

    #[test]
    fn paste_consumes_register() {
        let (_, edits) = run("\"ap");
        assert_eq!(
            edits,
            vec![Edit::PasteAfter {
                register: Some('a')
            }]
        );
    }

    #[test]
    fn f_find_forward_consumes_target() {
        let (_, edits) = run("fx");
        assert_eq!(
            edits,
            vec![Edit::ApplyMotion {
                motion: Motion::FindForward('x'),
                count: 1
            }]
        );
    }

    #[test]
    fn t_till_forward_consumes_target() {
        let (_, edits) = run("ty");
        assert_eq!(
            edits,
            vec![Edit::ApplyMotion {
                motion: Motion::TillForward('y'),
                count: 1
            }]
        );
    }

    #[test]
    fn insert_then_esc_round_trip() {
        let mut v = Vim::new();
        let e1 = v.on_stroke(Stroke::Char('i'));
        assert_eq!(e1, vec![Edit::EnterMode(Mode::Insert)]);
        let e2 = v.on_stroke(Stroke::Char('h'));
        assert_eq!(e2, vec![Edit::InsertChar('h')]);
        let e3 = v.on_stroke(Stroke::Char('i'));
        assert_eq!(e3, vec![Edit::InsertChar('i')]);
        let e4 = v.on_stroke(Stroke::Esc);
        assert_eq!(e4, vec![Edit::EnterMode(Mode::Normal)]);
        assert_eq!(v.mode(), Mode::Normal);
    }

    #[test]
    fn open_line_below_enters_insert() {
        let (vim, edits) = run("o");
        assert_eq!(
            edits,
            vec![Edit::OpenLineBelow, Edit::EnterMode(Mode::Insert)]
        );
        assert_eq!(vim.mode(), Mode::Insert);
    }

    #[test]
    fn x_with_count_passes_count_through() {
        let (_, edits) = run("3x");
        assert_eq!(edits, vec![Edit::DeleteCharUnderCursor { count: 3 }]);
    }

    #[test]
    fn esc_cancels_operator_pending() {
        let mut v = Vim::new();
        let _ = v.on_stroke(Stroke::Char('d'));
        assert_eq!(v.mode(), Mode::OpPending);
        let _ = v.on_stroke(Stroke::Esc);
        assert_eq!(v.mode(), Mode::Normal);
    }

    #[test]
    fn unknown_key_in_op_pending_resets() {
        let mut v = Vim::new();
        let _ = v.on_stroke(Stroke::Char('d'));
        let _ = v.on_stroke(Stroke::Char('Z'));
        assert_eq!(v.mode(), Mode::Normal);
    }

    #[test]
    fn visual_mode_d_returns_to_normal_with_op() {
        let mut v = Vim::new();
        let _ = v.on_stroke(Stroke::Char('v'));
        assert_eq!(v.mode(), Mode::Visual);
        let edits = v.on_stroke(Stroke::Char('d'));
        assert_eq!(edits.len(), 2);
        assert!(matches!(edits[0], Edit::ApplyLinewise { .. }));
        assert_eq!(v.mode(), Mode::Normal);
    }

    #[test]
    fn undo_emits_undo_edit() {
        let (_, edits) = run("u");
        assert_eq!(edits, vec![Edit::Undo]);
    }

    #[test]
    fn shift_a_jumps_to_eol_then_inserts() {
        let (vim, edits) = run("A");
        assert_eq!(
            edits,
            vec![
                Edit::ApplyMotion {
                    motion: Motion::LineEnd,
                    count: 1
                },
                Edit::EnterMode(Mode::Insert),
            ]
        );
        assert_eq!(vim.mode(), Mode::Insert);
    }
}
