//! Static capability matrix for known shells.
//!
//! Lookup table consumed by:
//!   - shell-integration installer: which dotfile to inject into.
//!   - `wok doctor`: report capability gaps (e.g. "$shell does not advertise
//!     OSC 133 → block detection unavailable").
//!   - shell-spawn: pick the right `--login` analogue.
//!
//! Data-only. Decoupled from `ShellType` so adding entries does not require
//! touching the rest of the codebase.

/// Statically-described capability set for a shell.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ShellCapability {
    /// Lowercase canonical shell name.
    pub name: &'static str,
    /// `true` if the shell can be wired to emit OSC 133 prompt markers.
    pub osc133: bool,
    /// Env-var that holds the prompt template (for `$PROMPT`/`$PS1` discovery).
    pub prompt_var: &'static str,
    /// History file path (relative to `$HOME`) when known.
    pub history_file: &'static str,
    /// Per-user startup file (relative to `$HOME`) where integration is sourced.
    pub profile_path: &'static str,
    /// File where aliases are typically defined (relative to `$HOME`).
    pub alias_file: &'static str,
    /// `true` if Wok ships a first-party integration script for this shell.
    pub has_integration: bool,
}

const NONE: &str = "";

/// All known shell entries. POSIX-family first.
pub const SHELL_CAPABILITIES: &[ShellCapability] = &[
    ShellCapability {
        name: "bash",
        osc133: true,
        prompt_var: "PS1",
        history_file: ".bash_history",
        profile_path: ".bashrc",
        alias_file: ".bash_aliases",
        has_integration: true,
    },
    ShellCapability {
        name: "zsh",
        osc133: true,
        prompt_var: "PS1",
        history_file: ".zsh_history",
        profile_path: ".zshrc",
        alias_file: ".zshrc",
        has_integration: true,
    },
    ShellCapability {
        name: "fish",
        osc133: true,
        prompt_var: "fish_prompt",
        history_file: ".local/share/fish/fish_history",
        profile_path: ".config/fish/config.fish",
        alias_file: ".config/fish/config.fish",
        has_integration: true,
    },
    ShellCapability {
        name: "ash",
        osc133: false,
        prompt_var: "PS1",
        history_file: ".ash_history",
        profile_path: ".profile",
        alias_file: ".profile",
        has_integration: false,
    },
    ShellCapability {
        name: "dash",
        osc133: false,
        prompt_var: "PS1",
        history_file: NONE,
        profile_path: ".profile",
        alias_file: ".profile",
        has_integration: false,
    },
    ShellCapability {
        name: "ksh",
        osc133: false,
        prompt_var: "PS1",
        history_file: ".sh_history",
        profile_path: ".kshrc",
        alias_file: ".kshrc",
        has_integration: false,
    },
    ShellCapability {
        name: "csh",
        osc133: false,
        prompt_var: "prompt",
        history_file: ".history",
        profile_path: ".cshrc",
        alias_file: ".cshrc",
        has_integration: false,
    },
    ShellCapability {
        name: "tcsh",
        osc133: false,
        prompt_var: "prompt",
        history_file: ".history",
        profile_path: ".tcshrc",
        alias_file: ".tcshrc",
        has_integration: false,
    },
    ShellCapability {
        name: "nu",
        osc133: true,
        prompt_var: "PROMPT_COMMAND",
        history_file: ".config/nushell/history.txt",
        profile_path: ".config/nushell/config.nu",
        alias_file: ".config/nushell/config.nu",
        has_integration: false,
    },
    ShellCapability {
        name: "xonsh",
        osc133: false,
        prompt_var: "PROMPT",
        history_file: ".local/share/xonsh/history.json",
        profile_path: ".xonshrc",
        alias_file: ".xonshrc",
        has_integration: false,
    },
    ShellCapability {
        name: "elvish",
        osc133: true,
        prompt_var: "edit:prompt",
        history_file: ".local/state/elvish/db.bolt",
        profile_path: ".config/elvish/rc.elv",
        alias_file: ".config/elvish/rc.elv",
        has_integration: false,
    },
    ShellCapability {
        name: "powershell",
        osc133: true,
        prompt_var: "prompt",
        history_file: NONE,
        profile_path: NONE,
        alias_file: NONE,
        has_integration: false,
    },
];

/// Lookup by exact lowercase shell name. Returns `None` for unknown shells.
pub fn lookup(name: &str) -> Option<&'static ShellCapability> {
    SHELL_CAPABILITIES.iter().find(|c| c.name == name)
}

/// Names of all shells with first-party integration scripts.
pub fn integrated_shell_names() -> Vec<&'static str> {
    SHELL_CAPABILITIES
        .iter()
        .filter(|c| c.has_integration)
        .map(|c| c.name)
        .collect()
}

/// Names of all shells that can advertise OSC 133.
pub fn osc133_capable_names() -> Vec<&'static str> {
    SHELL_CAPABILITIES
        .iter()
        .filter(|c| c.osc133)
        .map(|c| c.name)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn core_shells_present() {
        for name in ["bash", "zsh", "fish", "powershell"] {
            assert!(lookup(name).is_some(), "missing {name}");
        }
    }

    #[test]
    fn extended_shells_present() {
        for name in ["nu", "xonsh", "elvish", "ash", "dash", "ksh", "csh", "tcsh"] {
            assert!(lookup(name).is_some(), "missing {name}");
        }
    }

    #[test]
    fn unknown_returns_none() {
        assert!(lookup("foobar").is_none());
    }

    #[test]
    fn integrated_subset_includes_bash_zsh_fish() {
        let names = integrated_shell_names();
        for n in ["bash", "zsh", "fish"] {
            assert!(names.contains(&n), "expected {n} integrated");
        }
        assert!(!names.contains(&"ksh"));
    }

    #[test]
    fn osc133_set_excludes_pure_posix_shells() {
        let names = osc133_capable_names();
        assert!(names.contains(&"bash"));
        assert!(names.contains(&"zsh"));
        assert!(!names.contains(&"dash"));
        assert!(!names.contains(&"csh"));
    }

    #[test]
    fn names_are_unique() {
        let mut seen: Vec<&str> = SHELL_CAPABILITIES.iter().map(|c| c.name).collect();
        seen.sort_unstable();
        let original_len = seen.len();
        seen.dedup();
        assert_eq!(seen.len(), original_len);
    }

    #[test]
    fn integration_implies_osc133() {
        for c in SHELL_CAPABILITIES {
            if c.has_integration {
                assert!(c.osc133, "{} integrated but no OSC 133", c.name);
            }
        }
    }
}
