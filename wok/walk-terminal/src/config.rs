//! Terminal configuration: configurable options for terminal emulation.

use alacritty_terminal::term::Config;

/// Configuration for a terminal instance.
#[derive(Debug, Clone)]
pub struct TerminalConfig {
    /// Number of scrollback lines to retain.
    pub scrollback_lines: usize,
    /// Whether to wrap text at terminal width.
    pub text_wrap: bool,
    /// Width of Unicode ambiguous-width characters (1 or 2).
    pub unicode_ambiguous_width: u16,
}

impl Default for TerminalConfig {
    fn default() -> Self {
        Self {
            scrollback_lines: 10_000,
            text_wrap: true,
            unicode_ambiguous_width: 1,
        }
    }
}

impl TerminalConfig {
    /// Convert to alacritty_terminal's Config.
    pub fn to_alacritty_config(&self) -> Config {
        Config {
            scrolling_history: self.scrollback_lines,
            ..Config::default()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = TerminalConfig::default();
        assert_eq!(config.scrollback_lines, 10_000);
        assert!(config.text_wrap);
        assert_eq!(config.unicode_ambiguous_width, 1);
    }

    #[test]
    fn test_to_alacritty_config() {
        let mut config = TerminalConfig::default();
        config.scrollback_lines = 50_000;
        let alacritty_config = config.to_alacritty_config();
        assert_eq!(alacritty_config.scrolling_history, 50_000);
    }
}
