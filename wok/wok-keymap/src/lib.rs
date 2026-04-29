//! Context-scoped chord-tree keymap resolver.
//!
//! A binding is `(sequence: Vec<Stroke>, action: ActionId, when:
//! ContextPredicate)`. The resolver feeds strokes one at a time and returns:
//!   - [`Resolution::Match`] — the buffered sequence matched a binding.
//!   - [`Resolution::Pending`] — the buffer is a strict prefix of one or more
//!     bindings; caller should keep buffering.
//!   - [`Resolution::None`] — no binding matches; caller should flush.
//!
//! Conflict arbitration (longer sequence wins; later-registered binding wins
//! for equal-length sequences in the same context) keeps the chord tree
//! deterministic.

#![deny(missing_docs)]
#![forbid(unsafe_code)]

use std::collections::HashSet;

/// Modifier flags. Combinable.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub struct Mods {
    /// Control.
    pub ctrl: bool,
    /// Shift.
    pub shift: bool,
    /// Alt / Option.
    pub alt: bool,
    /// Super / Meta / Cmd.
    pub super_: bool,
}

impl Mods {
    /// No modifiers.
    pub const NONE: Self = Self {
        ctrl: false,
        shift: false,
        alt: false,
        super_: false,
    };

    /// Builder helpers.
    pub const fn ctrl() -> Self {
        Self {
            ctrl: true,
            ..Self::NONE
        }
    }
    /// Cmd / Super.
    pub const fn cmd() -> Self {
        Self {
            super_: true,
            ..Self::NONE
        }
    }
    /// Shift.
    pub const fn shift() -> Self {
        Self {
            shift: true,
            ..Self::NONE
        }
    }
}

/// One canonical key + modifiers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Stroke {
    /// Lowercase ASCII letter or digit, or symbolic key name.
    pub key: Key,
    /// Modifier flags.
    pub mods: Mods,
}

impl Stroke {
    /// Build a plain stroke (no modifiers).
    pub const fn plain(key: Key) -> Self {
        Self {
            key,
            mods: Mods::NONE,
        }
    }
    /// Build a stroke from key + mods.
    pub const fn new(key: Key, mods: Mods) -> Self {
        Self { key, mods }
    }
}

/// Key identifier.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Key {
    /// Single ASCII char (lowercased letters preferred).
    Char(char),
    /// Enter / Return.
    Enter,
    /// Escape.
    Esc,
    /// Tab.
    Tab,
    /// Backspace.
    Backspace,
    /// Space.
    Space,
}

/// Action identifier — opaque string.
pub type ActionId = &'static str;

/// Context tags (e.g. `"workspace"`, `"pane"`, `"editor"`). The resolver
/// matches predicates against this set.
pub type Context = HashSet<&'static str>;

/// Predicate over the active context tags.
#[derive(Debug, Clone)]
pub enum ContextPredicate {
    /// Always matches.
    Any,
    /// Matches if all named tags are active.
    All(Vec<&'static str>),
    /// Matches if any named tag is active.
    AnyOf(Vec<&'static str>),
    /// Matches if no named tag is active.
    None_(Vec<&'static str>),
}

impl ContextPredicate {
    fn matches(&self, ctx: &Context) -> bool {
        match self {
            Self::Any => true,
            Self::All(tags) => tags.iter().all(|t| ctx.contains(t)),
            Self::AnyOf(tags) => tags.iter().any(|t| ctx.contains(t)),
            Self::None_(tags) => tags.iter().all(|t| !ctx.contains(t)),
        }
    }
}

/// One key binding.
#[derive(Debug, Clone)]
pub struct Binding {
    /// Sequence of strokes that triggers `action`.
    pub sequence: Vec<Stroke>,
    /// Action identifier.
    pub action: ActionId,
    /// When the binding is active.
    pub when: ContextPredicate,
}

/// Outcome of one [`Keymap::feed`] call.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Resolution {
    /// `sequence_len` strokes matched `action`.
    Match {
        /// Action id.
        action: ActionId,
        /// Number of strokes consumed.
        sequence_len: usize,
    },
    /// Buffer is a strict prefix of at least one binding.
    Pending,
    /// No binding matches the buffered prefix.
    None,
}

/// Keymap container.
#[derive(Debug, Clone, Default)]
pub struct Keymap {
    bindings: Vec<Binding>,
}

impl Keymap {
    /// Empty keymap.
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a binding. Bindings registered later beat earlier ones for equal
    /// sequence length in the same context.
    pub fn bind(&mut self, b: Binding) {
        self.bindings.push(b);
    }

    /// Number of bindings.
    pub fn len(&self) -> usize {
        self.bindings.len()
    }

    /// Whether the map has no bindings.
    pub fn is_empty(&self) -> bool {
        self.bindings.is_empty()
    }

    /// Resolve a stroke buffer against the active context.
    pub fn resolve(&self, buffer: &[Stroke], ctx: &Context) -> Resolution {
        if buffer.is_empty() {
            return Resolution::None;
        }
        let mut best: Option<&Binding> = None;
        let mut has_pending = false;
        for b in &self.bindings {
            if !b.when.matches(ctx) {
                continue;
            }
            if b.sequence.len() < buffer.len() {
                continue;
            }
            if &b.sequence[..buffer.len()] != buffer {
                continue;
            }
            if b.sequence.len() == buffer.len() {
                // exact match — later bindings overwrite earlier ones at the
                // same length (registration order = priority).
                best = Some(b);
            } else {
                has_pending = true;
            }
        }
        if let Some(b) = best {
            // a longer pending binding still beats an exact match — let the
            // caller buffer one more stroke before committing.
            if has_pending {
                Resolution::Pending
            } else {
                Resolution::Match {
                    action: b.action,
                    sequence_len: b.sequence.len(),
                }
            }
        } else if has_pending {
            Resolution::Pending
        } else {
            Resolution::None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stroke(c: char) -> Stroke {
        Stroke::plain(Key::Char(c))
    }

    fn ctx(tags: &[&'static str]) -> Context {
        tags.iter().copied().collect()
    }

    fn empty_ctx() -> Context {
        Context::new()
    }

    #[test]
    fn unknown_buffer_resolves_none() {
        let m = Keymap::new();
        assert_eq!(m.resolve(&[stroke('a')], &empty_ctx()), Resolution::None);
    }

    #[test]
    fn exact_match_returns_match() {
        let mut m = Keymap::new();
        m.bind(Binding {
            sequence: vec![stroke('g'), stroke('s')],
            action: "git.status",
            when: ContextPredicate::Any,
        });
        assert_eq!(
            m.resolve(&[stroke('g'), stroke('s')], &empty_ctx()),
            Resolution::Match {
                action: "git.status",
                sequence_len: 2
            }
        );
    }

    #[test]
    fn prefix_returns_pending() {
        let mut m = Keymap::new();
        m.bind(Binding {
            sequence: vec![stroke('g'), stroke('s')],
            action: "git.status",
            when: ContextPredicate::Any,
        });
        assert_eq!(m.resolve(&[stroke('g')], &empty_ctx()), Resolution::Pending);
    }

    #[test]
    fn longer_sequence_blocks_short_match_until_disambiguated() {
        let mut m = Keymap::new();
        m.bind(Binding {
            sequence: vec![stroke('g')],
            action: "go",
            when: ContextPredicate::Any,
        });
        m.bind(Binding {
            sequence: vec![stroke('g'), stroke('g')],
            action: "go.go",
            when: ContextPredicate::Any,
        });
        // exact `g` is a match, but `gg` is also pending — caller should wait.
        assert_eq!(m.resolve(&[stroke('g')], &empty_ctx()), Resolution::Pending);
        assert_eq!(
            m.resolve(&[stroke('g'), stroke('g')], &empty_ctx()),
            Resolution::Match {
                action: "go.go",
                sequence_len: 2
            }
        );
    }

    #[test]
    fn context_filters_bindings() {
        let mut m = Keymap::new();
        m.bind(Binding {
            sequence: vec![stroke('q')],
            action: "quit.editor",
            when: ContextPredicate::All(vec!["editor"]),
        });
        m.bind(Binding {
            sequence: vec![stroke('q')],
            action: "quit.workspace",
            when: ContextPredicate::All(vec!["workspace"]),
        });
        let buf = [stroke('q')];
        let r1 = m.resolve(&buf, &ctx(&["editor"]));
        assert!(
            matches!(r1, Resolution::Match { action, .. } if action == "quit.editor"),
            "got {r1:?}"
        );
        let r2 = m.resolve(&buf, &ctx(&["workspace"]));
        assert!(matches!(r2, Resolution::Match { action, .. } if action == "quit.workspace"));
        let r3 = m.resolve(&buf, &empty_ctx());
        assert_eq!(r3, Resolution::None);
    }

    #[test]
    fn later_binding_wins_at_same_length() {
        let mut m = Keymap::new();
        m.bind(Binding {
            sequence: vec![stroke('a')],
            action: "first",
            when: ContextPredicate::Any,
        });
        m.bind(Binding {
            sequence: vec![stroke('a')],
            action: "second",
            when: ContextPredicate::Any,
        });
        let r = m.resolve(&[stroke('a')], &empty_ctx());
        assert!(matches!(r, Resolution::Match { action, .. } if action == "second"));
    }

    #[test]
    fn modifiers_distinguish_strokes() {
        let mut m = Keymap::new();
        m.bind(Binding {
            sequence: vec![Stroke::plain(Key::Char('s'))],
            action: "save",
            when: ContextPredicate::Any,
        });
        m.bind(Binding {
            sequence: vec![Stroke::new(Key::Char('s'), Mods::cmd())],
            action: "cmd.save",
            when: ContextPredicate::Any,
        });
        assert!(matches!(
            m.resolve(&[Stroke::plain(Key::Char('s'))], &empty_ctx()),
            Resolution::Match { action: "save", .. }
        ));
        assert!(matches!(
            m.resolve(&[Stroke::new(Key::Char('s'), Mods::cmd())], &empty_ctx()),
            Resolution::Match {
                action: "cmd.save",
                ..
            }
        ));
    }

    #[test]
    fn anyof_predicate() {
        let mut m = Keymap::new();
        m.bind(Binding {
            sequence: vec![stroke('p')],
            action: "palette",
            when: ContextPredicate::AnyOf(vec!["editor", "search"]),
        });
        assert!(matches!(
            m.resolve(&[stroke('p')], &ctx(&["search"])),
            Resolution::Match { .. }
        ));
        assert_eq!(m.resolve(&[stroke('p')], &empty_ctx()), Resolution::None);
    }

    #[test]
    fn none_predicate_excludes_when_tag_present() {
        let mut m = Keymap::new();
        m.bind(Binding {
            sequence: vec![stroke('q')],
            action: "quit",
            when: ContextPredicate::None_(vec!["modal"]),
        });
        assert!(matches!(
            m.resolve(&[stroke('q')], &empty_ctx()),
            Resolution::Match { .. }
        ));
        assert_eq!(m.resolve(&[stroke('q')], &ctx(&["modal"])), Resolution::None);
    }
}
