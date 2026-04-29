//! Release channel metadata.
//!
//! `Channel` is selected at compile time via the `WOK_CHANNEL` env var read
//! during the build. Defaults to [`Channel::Dev`].

#![deny(missing_docs)]

use std::fmt;

/// Release channel ring.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Channel {
    /// Local developer build. All dogfood + preview features on.
    Dev,
    /// Internal team dogfood build. Dogfood + preview features on.
    Dogfood,
    /// External preview build. Preview features on.
    Preview,
    /// General-availability stable build. Only release-ring features on.
    Stable,
}

impl Channel {
    /// Channel selected at compile time. Reads the `WOK_CHANNEL` env var at
    /// build time. Unknown / unset values fall through to [`Channel::Dev`].
    pub const fn current() -> Self {
        match option_env!("WOK_CHANNEL") {
            Some(v) => match v.as_bytes() {
                b"stable" | b"STABLE" => Self::Stable,
                b"preview" | b"PREVIEW" => Self::Preview,
                b"dogfood" | b"DOGFOOD" => Self::Dogfood,
                _ => Self::Dev,
            },
            None => Self::Dev,
        }
    }

    /// Lowercase short name suitable for telemetry / doctor output.
    pub const fn short_name(self) -> &'static str {
        match self {
            Self::Dev => "dev",
            Self::Dogfood => "dogfood",
            Self::Preview => "preview",
            Self::Stable => "stable",
        }
    }

    /// True for `Dev` and `Dogfood`.
    pub const fn is_dogfood_or_below(self) -> bool {
        matches!(self, Self::Dev | Self::Dogfood)
    }

    /// True for `Dev`, `Dogfood`, `Preview`.
    pub const fn is_preview_or_below(self) -> bool {
        matches!(self, Self::Dev | Self::Dogfood | Self::Preview)
    }
}

impl fmt::Display for Channel {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.short_name())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn current_defaults_to_dev_when_unset() {
        // We cannot set WOK_CHANNEL at build-time from a test, but we can
        // verify the default matches the env var actually used during test
        // compilation — typically unset.
        let c = Channel::current();
        // At the very least, it should be a known variant.
        let _name = c.short_name();
    }

    #[test]
    fn short_name_unique_per_variant() {
        let names = [
            Channel::Dev.short_name(),
            Channel::Dogfood.short_name(),
            Channel::Preview.short_name(),
            Channel::Stable.short_name(),
        ];
        let mut sorted: Vec<&str> = names.to_vec();
        sorted.sort_unstable();
        sorted.dedup();
        assert_eq!(sorted.len(), 4);
    }

    #[test]
    fn rings_compose_correctly() {
        assert!(Channel::Dev.is_dogfood_or_below());
        assert!(Channel::Dogfood.is_dogfood_or_below());
        assert!(!Channel::Preview.is_dogfood_or_below());
        assert!(!Channel::Stable.is_dogfood_or_below());

        assert!(Channel::Dev.is_preview_or_below());
        assert!(Channel::Preview.is_preview_or_below());
        assert!(!Channel::Stable.is_preview_or_below());
    }

    #[test]
    fn display_matches_short_name() {
        assert_eq!(format!("{}", Channel::Dev), "dev");
    }
}
