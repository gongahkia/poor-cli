//! Feature flag rings.
//!
//! Each [`FeatureFlag`] is on or off based on:
//!   1. The build's [`wok_channels::Channel`] and the ring arrays below.
//!   2. The `WOK_FLAGS` env var, which can force-enable (`+Name`) or
//!      force-disable (`-Name`) any flag.
//!
//! Example: `WOK_FLAGS=+UnifiedInput,-SumTreeScrollback`.
//!
//! Adding a flag = add the variant to [`FeatureFlag`], pick the highest ring
//! it should ride in (`RELEASE_FLAGS` ⊃ `PREVIEW_FLAGS` ⊃ `DOGFOOD_FLAGS`),
//! and add a one-line entry in `docs/FEATURE_FLAGS.md` (TODO).

#![deny(missing_docs)]

use wok_channels::Channel;

/// Known feature flags. Add new variants here only.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[non_exhaustive]
pub enum FeatureFlag {
    /// P3.3 — single editor surface that routes to shell/search/palette.
    UnifiedInput,
    /// P2.3 — sum-tree-backed scrollback in `wok-terminal`.
    SumTreeScrollback,
    /// P3.2 — provider-based completion engine.
    ProviderCompletion,
    /// P7.1 — block filtering UI.
    BlockFiltering,
}

impl FeatureFlag {
    /// Stable short name used in `WOK_FLAGS` and telemetry.
    pub const fn name(self) -> &'static str {
        match self {
            Self::UnifiedInput => "UnifiedInput",
            Self::SumTreeScrollback => "SumTreeScrollback",
            Self::ProviderCompletion => "ProviderCompletion",
            Self::BlockFiltering => "BlockFiltering",
        }
    }

    /// All known flags. Order is stable but not significant.
    pub const fn all() -> &'static [Self] {
        &[
            Self::UnifiedInput,
            Self::SumTreeScrollback,
            Self::ProviderCompletion,
            Self::BlockFiltering,
        ]
    }

    /// Default-on for dogfood and below.
    pub const fn dogfood_flags() -> &'static [Self] {
        &[]
    }

    /// Default-on for preview and below.
    pub const fn preview_flags() -> &'static [Self] {
        &[]
    }

    /// Default-on for stable.
    pub const fn release_flags() -> &'static [Self] {
        &[]
    }

    /// Whether this flag is currently enabled. Reads `WOK_FLAGS` first, then
    /// falls back to the channel's ring membership.
    pub fn is_enabled(self) -> bool {
        if let Ok(spec) = std::env::var("WOK_FLAGS") {
            if let Some(forced) = parse_force(&spec, self.name()) {
                return forced;
            }
        }
        let ch = Channel::current();
        in_ring(self, ch)
    }
}

fn in_ring(flag: FeatureFlag, channel: Channel) -> bool {
    let mut rings: Vec<&[FeatureFlag]> = vec![FeatureFlag::release_flags()];
    if channel.is_preview_or_below() {
        rings.push(FeatureFlag::preview_flags());
    }
    if channel.is_dogfood_or_below() {
        rings.push(FeatureFlag::dogfood_flags());
    }
    rings.iter().any(|ring| ring.contains(&flag))
}

fn parse_force(spec: &str, name: &str) -> Option<bool> {
    for token in spec.split(',') {
        let token = token.trim();
        if let Some(rest) = token.strip_prefix('+') {
            if rest.eq_ignore_ascii_case(name) {
                return Some(true);
            }
        } else if let Some(rest) = token.strip_prefix('-') {
            if rest.eq_ignore_ascii_case(name) {
                return Some(false);
            }
        }
    }
    None
}

/// Snapshot of all flags as `(name, enabled)` pairs. For doctor / debug dumps.
pub fn snapshot() -> Vec<(&'static str, bool)> {
    FeatureFlag::all()
        .iter()
        .map(|&f| (f.name(), f.is_enabled()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn with_env<R>(key: &str, val: Option<&str>, f: impl FnOnce() -> R) -> R {
        let prev = std::env::var(key).ok();
        match val {
            Some(v) => std::env::set_var(key, v),
            None => std::env::remove_var(key),
        }
        let r = f();
        match prev {
            Some(p) => std::env::set_var(key, p),
            None => std::env::remove_var(key),
        }
        r
    }

    #[test]
    fn unknown_flag_in_spec_does_not_force() {
        assert_eq!(parse_force("+Other", "UnifiedInput"), None);
    }

    #[test]
    fn plus_force_enables() {
        assert_eq!(parse_force("+UnifiedInput", "UnifiedInput"), Some(true));
    }

    #[test]
    fn minus_force_disables() {
        assert_eq!(parse_force("-UnifiedInput", "UnifiedInput"), Some(false));
    }

    #[test]
    fn case_insensitive_match() {
        assert_eq!(parse_force("+unifiedinput", "UnifiedInput"), Some(true));
    }

    #[test]
    fn force_overrides_default() {
        with_env("WOK_FLAGS", Some("+UnifiedInput"), || {
            assert!(FeatureFlag::UnifiedInput.is_enabled());
        });
        with_env("WOK_FLAGS", Some("-UnifiedInput"), || {
            assert!(!FeatureFlag::UnifiedInput.is_enabled());
        });
    }

    #[test]
    fn snapshot_lists_every_flag() {
        let snap = snapshot();
        assert_eq!(snap.len(), FeatureFlag::all().len());
    }

    #[test]
    fn names_are_unique() {
        let names: Vec<_> = FeatureFlag::all().iter().map(|f| f.name()).collect();
        let mut sorted = names.clone();
        sorted.sort_unstable();
        sorted.dedup();
        assert_eq!(sorted.len(), names.len());
    }
}
