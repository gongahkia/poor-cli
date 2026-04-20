//! Prompt framework detection: detects Starship, P10k, Oh-My-Posh, etc.

use std::collections::HashMap;
use std::path::PathBuf;

use crate::shell::ShellType;

/// Known prompt frameworks.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PromptFramework {
    /// Starship prompt.
    Starship,
    /// Powerlevel10k (Zsh).
    P10k,
    /// Oh My Posh.
    OhMyPosh,
    /// Oh My Zsh.
    OhMyZsh,
    /// Spaceship prompt.
    Spaceship,
    /// Custom/unknown framework.
    Custom,
}

/// Detect the active prompt framework.
pub fn detect_prompt_framework(_shell: &ShellType) -> Option<PromptFramework> {
    // Check for Starship
    if which("starship") {
        return Some(PromptFramework::Starship);
    }

    // Check for P10k
    if std::env::var("P10K_PROMPT").is_ok() || home_file_exists(".p10k.zsh") {
        return Some(PromptFramework::P10k);
    }

    // Check for Oh My Posh
    if which("oh-my-posh") {
        return Some(PromptFramework::OhMyPosh);
    }

    // Check for Oh My Zsh
    if std::env::var("ZSH").is_ok() {
        return Some(PromptFramework::OhMyZsh);
    }

    None
}

/// Configure environment variables for detected prompt framework.
pub fn configure_env_for_prompt(framework: &PromptFramework) -> HashMap<String, String> {
    let mut env = HashMap::new();
    env.insert("TERM".to_string(), "xterm-256color".to_string());
    env.insert("COLORTERM".to_string(), "truecolor".to_string());

    if *framework == PromptFramework::Starship && std::env::var("STARSHIP_SHELL").is_err() {
        env.insert("STARSHIP_SHELL".to_string(), "bash".to_string());
    }

    env
}

fn which(name: &str) -> bool {
    std::env::var("PATH")
        .map(|path| {
            path.split(':')
                .any(|dir| PathBuf::from(dir).join(name).exists())
        })
        .unwrap_or(false)
}

fn home_file_exists(name: &str) -> bool {
    std::env::var("HOME")
        .map(|h| PathBuf::from(h).join(name).exists())
        .unwrap_or(false)
}
