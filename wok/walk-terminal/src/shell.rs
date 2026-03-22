//! Shell detection and configuration.

use std::collections::HashMap;
use std::path::PathBuf;

/// Supported shell types.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ShellType {
    /// Bourne Again Shell.
    Bash,
    /// Z Shell.
    Zsh,
    /// Fish Shell.
    Fish,
    /// PowerShell.
    PowerShell,
    /// Windows Subsystem for Linux with a specific distro.
    Wsl(String),
}

impl std::fmt::Display for ShellType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Bash => write!(f, "bash"),
            Self::Zsh => write!(f, "zsh"),
            Self::Fish => write!(f, "fish"),
            Self::PowerShell => write!(f, "powershell"),
            Self::Wsl(distro) => write!(f, "wsl:{distro}"),
        }
    }
}

/// Configuration for spawning a shell process.
#[derive(Debug, Clone)]
pub struct PtyConfig {
    /// Path to the shell executable.
    pub shell: String,
    /// Arguments to pass to the shell.
    pub args: Vec<String>,
    /// Environment variables to set.
    pub env: HashMap<String, String>,
}

/// Detect the user's default shell.
///
/// On Unix, reads `$SHELL`. On Windows, defaults to PowerShell.
pub fn detect_default_shell() -> ShellType {
    #[cfg(unix)]
    {
        if let Ok(shell) = std::env::var("SHELL") {
            let basename = std::path::Path::new(&shell)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("bash");
            return match basename {
                "zsh" => ShellType::Zsh,
                "fish" => ShellType::Fish,
                _ => ShellType::Bash,
            };
        }
        ShellType::Bash
    }
    #[cfg(windows)]
    {
        ShellType::PowerShell
    }
}

/// Get the spawn configuration for a given shell type.
pub fn shell_spawn_config(shell: &ShellType) -> PtyConfig {
    let mut env = HashMap::new();
    env.insert("TERM".to_string(), "xterm-256color".to_string());
    env.insert("COLORTERM".to_string(), "truecolor".to_string());

    match shell {
        ShellType::Bash => PtyConfig {
            shell: find_shell("bash").unwrap_or_else(|| "/bin/bash".to_string()),
            args: vec!["--login".to_string()],
            env,
        },
        ShellType::Zsh => PtyConfig {
            shell: find_shell("zsh").unwrap_or_else(|| "/bin/zsh".to_string()),
            args: vec!["--login".to_string()],
            env,
        },
        ShellType::Fish => PtyConfig {
            shell: find_shell("fish").unwrap_or_else(|| "/usr/bin/fish".to_string()),
            args: vec!["--login".to_string()],
            env,
        },
        ShellType::PowerShell => PtyConfig {
            shell: "powershell.exe".to_string(),
            args: vec!["-NoLogo".to_string()],
            env,
        },
        ShellType::Wsl(distro) => PtyConfig {
            shell: "wsl.exe".to_string(),
            args: vec![
                "-d".to_string(),
                distro.clone(),
                "--".to_string(),
                "bash".to_string(),
                "--login".to_string(),
            ],
            env,
        },
    }
}

/// Scan the system for available shells.
pub fn available_shells() -> Vec<ShellType> {
    let mut shells = Vec::new();

    #[cfg(unix)]
    {
        if find_shell("bash").is_some() {
            shells.push(ShellType::Bash);
        }
        if find_shell("zsh").is_some() {
            shells.push(ShellType::Zsh);
        }
        if find_shell("fish").is_some() {
            shells.push(ShellType::Fish);
        }
    }

    #[cfg(windows)]
    {
        shells.push(ShellType::PowerShell);
    }

    if shells.is_empty() {
        shells.push(ShellType::Bash); // fallback
    }

    shells
}

/// Find a shell binary in PATH.
fn find_shell(name: &str) -> Option<String> {
    // Check common paths first
    let common_paths: &[&str] = &["/bin/", "/usr/bin/", "/usr/local/bin/"];

    for prefix in common_paths {
        let path = format!("{prefix}{name}");
        if PathBuf::from(&path).exists() {
            return Some(path);
        }
    }

    // Fall back to searching PATH
    if let Ok(path_var) = std::env::var("PATH") {
        for dir in path_var.split(':') {
            let full_path = PathBuf::from(dir).join(name);
            if full_path.exists() {
                return full_path.to_str().map(String::from);
            }
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_default_shell() {
        let shell = detect_default_shell();
        // Should return a valid shell type
        matches!(
            shell,
            ShellType::Bash | ShellType::Zsh | ShellType::Fish | ShellType::PowerShell
        );
    }

    #[test]
    fn test_shell_spawn_config_has_term() {
        let config = shell_spawn_config(&ShellType::Bash);
        assert_eq!(config.env.get("TERM").unwrap(), "xterm-256color");
        assert_eq!(config.env.get("COLORTERM").unwrap(), "truecolor");
    }

    #[test]
    fn test_available_shells_not_empty() {
        let shells = available_shells();
        assert!(!shells.is_empty());
    }

    #[test]
    fn test_shell_display() {
        assert_eq!(ShellType::Bash.to_string(), "bash");
        assert_eq!(ShellType::Zsh.to_string(), "zsh");
        assert_eq!(
            ShellType::Wsl("Ubuntu".to_string()).to_string(),
            "wsl:Ubuntu"
        );
    }
}
