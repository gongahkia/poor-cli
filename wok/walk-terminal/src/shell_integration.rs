//! Shell integration scripts: emit OSC 133 markers for block detection.

use crate::shell::ShellType;

/// Bash shell integration script (OSC 133 markers).
pub const BASH_INTEGRATION: &str = r#"
# Walk terminal shell integration (bash)
__walk_prompt_command() {
    local exit_code=$?
    printf '\033]133;D;%d\007' "$exit_code"
    printf '\033]133;A\007'
    printf '\033]7;file://%s%s\007' "$(hostname)" "$(pwd)"
}
__walk_preexec() {
    printf '\033]133;C\007'
}
PROMPT_COMMAND="__walk_prompt_command${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
trap '__walk_preexec' DEBUG
printf '\033]133;A\007'
"#;

/// Zsh shell integration script (OSC 133 markers).
pub const ZSH_INTEGRATION: &str = r#"
# Walk terminal shell integration (zsh)
__walk_precmd() {
    local exit_code=$?
    printf '\033]133;D;%d\007' "$exit_code"
    printf '\033]133;A\007'
    printf '\033]7;file://%s%s\007' "$(hostname)" "$(pwd)"
}
__walk_preexec() {
    printf '\033]133;B\007'
    printf '\033]133;C\007'
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd __walk_precmd
add-zsh-hook preexec __walk_preexec
printf '\033]133;A\007'
"#;

/// Fish shell integration script (OSC 133 markers).
pub const FISH_INTEGRATION: &str = r#"
# Walk terminal shell integration (fish)
function __walk_prompt --on-event fish_prompt
    printf '\033]133;D;%d\007' $status
    printf '\033]133;A\007'
    printf '\033]7;file://%s%s\007' (hostname) (pwd)
end
function __walk_preexec --on-event fish_preexec
    printf '\033]133;B\007'
    printf '\033]133;C\007'
end
printf '\033]133;A\007'
"#;

/// Return extra environment setup for shell integration.
///
/// This sets `WALK_SHELL_INTEGRATION` and `WALK_INTEGRATION_DIR` env vars
/// that the shell rc files can detect.
pub fn integration_env(shell: &ShellType) -> Vec<(String, String)> {
    let script = match shell {
        ShellType::Bash => BASH_INTEGRATION,
        ShellType::Zsh => ZSH_INTEGRATION,
        ShellType::Fish => FISH_INTEGRATION,
        _ => return Vec::new(),
    };

    vec![
        ("WALK_SHELL_INTEGRATION".to_string(), "1".to_string()),
        ("WALK_INTEGRATION_SCRIPT".to_string(), script.to_string()),
    ]
}

/// Return shell-specific arguments to inject integration.
pub fn integration_args(shell: &ShellType) -> Vec<String> {
    match shell {
        ShellType::Bash => vec![
            "--rcfile".to_string(),
            "/dev/stdin".to_string(),
        ],
        _ => Vec::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bash_integration_has_osc_markers() {
        assert!(BASH_INTEGRATION.contains("133;A"));
        assert!(BASH_INTEGRATION.contains("133;C"));
        assert!(BASH_INTEGRATION.contains("133;D"));
    }

    #[test]
    fn test_zsh_integration_has_osc_markers() {
        assert!(ZSH_INTEGRATION.contains("133;A"));
        assert!(ZSH_INTEGRATION.contains("133;B"));
        assert!(ZSH_INTEGRATION.contains("133;C"));
        assert!(ZSH_INTEGRATION.contains("133;D"));
    }

    #[test]
    fn test_fish_integration_has_osc_markers() {
        assert!(FISH_INTEGRATION.contains("133;A"));
        assert!(FISH_INTEGRATION.contains("133;B"));
        assert!(FISH_INTEGRATION.contains("133;C"));
        assert!(FISH_INTEGRATION.contains("133;D"));
    }

    #[test]
    fn test_integration_env_for_bash() {
        let env = integration_env(&ShellType::Bash);
        assert!(env.iter().any(|(k, _)| k == "WALK_SHELL_INTEGRATION"));
    }
}
