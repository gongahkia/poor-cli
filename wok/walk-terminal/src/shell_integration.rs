//! Shell integration scripts and bootstrap helpers for block detection.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use tempfile::{NamedTempFile, TempDir};

use crate::shell::{PtyConfig, ShellType};

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
pub const FISH_INTEGRATION: &str = r"
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
";

/// Temporary shell bootstrap artifacts that must remain alive for the shell lifetime.
pub enum ShellBootstrap {
    /// Bash rcfile wrapper.
    Bash(NamedTempFile),
    /// Zsh dotfiles directory wrapper.
    Zsh(TempDir),
    /// Fish XDG config directory wrapper.
    Fish(TempDir),
}

/// Prepare shell bootstrap files and mutate the shell config to use them.
///
/// Returns `Ok(None)` for shells that do not yet support automatic Walk integration.
pub fn prepare_shell_bootstrap(
    shell: &ShellType,
    config: &mut PtyConfig,
) -> Result<Option<ShellBootstrap>, std::io::Error> {
    match shell {
        ShellType::Bash => prepare_bash_bootstrap(config).map(Some),
        ShellType::Zsh => prepare_zsh_bootstrap(config).map(Some),
        ShellType::Fish => prepare_fish_bootstrap(config).map(Some),
        ShellType::PowerShell | ShellType::Wsl(_) => Ok(None),
    }
}

fn prepare_bash_bootstrap(config: &mut PtyConfig) -> Result<ShellBootstrap, std::io::Error> {
    let home = home_dir();
    let bash_profile = shell_quote(&home.join(".bash_profile"));
    let bash_login = shell_quote(&home.join(".bash_login"));
    let profile = shell_quote(&home.join(".profile"));
    let bashrc = shell_quote(&home.join(".bashrc"));

    let mut rcfile = NamedTempFile::new()?;
    write!(
        rcfile,
        "\
# Walk shell bootstrap (bash)
if [ -f {bash_profile} ]; then
    . {bash_profile}
elif [ -f {bash_login} ]; then
    . {bash_login}
elif [ -f {profile} ]; then
    . {profile}
fi
if [ -f {bashrc} ]; then
    . {bashrc}
fi
{BASH_INTEGRATION}
"
    )?;

    config.args = vec![
        "--noprofile".to_string(),
        "--norc".to_string(),
        "--rcfile".to_string(),
        rcfile.path().to_string_lossy().into_owned(),
        "-i".to_string(),
    ];

    Ok(ShellBootstrap::Bash(rcfile))
}

fn prepare_zsh_bootstrap(config: &mut PtyConfig) -> Result<ShellBootstrap, std::io::Error> {
    let original = original_zdotdir();
    let tempdir = TempDir::new()?;
    let tempdir_path = tempdir.path();

    fs::write(
        tempdir_path.join(".zshenv"),
        format!(
            "# Walk shell bootstrap (zsh)\n{}",
            zsh_source_if_exists(&original.join(".zshenv"))
        ),
    )?;
    fs::write(
        tempdir_path.join(".zprofile"),
        zsh_source_if_exists(&original.join(".zprofile")),
    )?;
    fs::write(
        tempdir_path.join(".zshrc"),
        format!(
            "{}{}",
            zsh_source_if_exists(&original.join(".zshrc")),
            ZSH_INTEGRATION
        ),
    )?;
    fs::write(
        tempdir_path.join(".zlogin"),
        zsh_source_if_exists(&original.join(".zlogin")),
    )?;

    config.args = vec!["-i".to_string(), "--login".to_string()];
    config.env.insert(
        "ZDOTDIR".to_string(),
        tempdir_path.to_string_lossy().into_owned(),
    );

    Ok(ShellBootstrap::Zsh(tempdir))
}

fn prepare_fish_bootstrap(config: &mut PtyConfig) -> Result<ShellBootstrap, std::io::Error> {
    let original = xdg_config_home().join("fish").join("config.fish");
    let tempdir = TempDir::new()?;
    let fish_dir = tempdir.path().join("fish");
    fs::create_dir_all(&fish_dir)?;
    fs::write(
        fish_dir.join("config.fish"),
        format!("{}{}", fish_source_if_exists(&original), FISH_INTEGRATION),
    )?;

    config.args = vec!["-i".to_string(), "--login".to_string()];
    config.env.insert(
        "XDG_CONFIG_HOME".to_string(),
        tempdir.path().to_string_lossy().into_owned(),
    );

    Ok(ShellBootstrap::Fish(tempdir))
}

fn zsh_source_if_exists(path: &Path) -> String {
    let quoted = shell_quote(path);
    format!("if [ -f {quoted} ]; then\n    source {quoted}\nfi\n")
}

fn fish_source_if_exists(path: &Path) -> String {
    let quoted = shell_quote(path);
    format!("if test -f {quoted}\n    source {quoted}\nend\n")
}

fn shell_quote(path: &Path) -> String {
    format!("'{}'", path.to_string_lossy().replace('\'', "'\"'\"'"))
}

fn home_dir() -> PathBuf {
    std::env::var("HOME").map_or_else(|_| PathBuf::from("."), PathBuf::from)
}

fn original_zdotdir() -> PathBuf {
    std::env::var("ZDOTDIR").map_or_else(|_| home_dir(), PathBuf::from)
}

fn xdg_config_home() -> PathBuf {
    std::env::var("XDG_CONFIG_HOME").map_or_else(|_| home_dir().join(".config"), PathBuf::from)
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::*;
    use crate::shell::PtyConfig;

    fn test_config(shell: &str) -> PtyConfig {
        PtyConfig {
            shell: shell.to_string(),
            args: vec!["--login".to_string()],
            env: HashMap::new(),
        }
    }

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
    fn test_prepare_bash_bootstrap_sets_rcfile() {
        let mut config = test_config("bash");
        let bootstrap = prepare_shell_bootstrap(&ShellType::Bash, &mut config).unwrap();
        assert!(matches!(bootstrap, Some(ShellBootstrap::Bash(_))));
        assert!(config.args.iter().any(|arg| arg == "--rcfile"));
    }

    #[test]
    fn test_prepare_zsh_bootstrap_sets_zdotdir() {
        let mut config = test_config("zsh");
        let bootstrap = prepare_shell_bootstrap(&ShellType::Zsh, &mut config).unwrap();
        assert!(matches!(bootstrap, Some(ShellBootstrap::Zsh(_))));
        assert!(config.env.contains_key("ZDOTDIR"));
    }

    #[test]
    fn test_prepare_fish_bootstrap_sets_xdg_config_home() {
        let mut config = test_config("fish");
        let bootstrap = prepare_shell_bootstrap(&ShellType::Fish, &mut config).unwrap();
        assert!(matches!(bootstrap, Some(ShellBootstrap::Fish(_))));
        assert!(config.env.contains_key("XDG_CONFIG_HOME"));
    }
}
