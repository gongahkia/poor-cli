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
    printf '\033]133;E;%s\007' "$BASH_COMMAND"
    printf '\033]133;B\007'
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
    printf '\033]133;E;%s\007' "$1"
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
    printf '\033]133;E;%s\007' "$argv[1]"
    printf '\033]133;B\007'
    printf '\033]133;C\007'
end
printf '\033]133;A\007'
"#;

/// PowerShell shell integration script (OSC 133 markers).
pub const POWERSHELL_INTEGRATION: &str = r#"
# Walk terminal shell integration (powershell)
function global:prompt {
    $exitCode = if ($LASTEXITCODE -ne $null) { $LASTEXITCODE } else { 0 }
    $hostName = [System.Net.Dns]::GetHostName()
    $cwd = (Get-Location).Path
    [Console]::Out.Write("`e]133;D;$exitCode`a")
    [Console]::Out.Write("`e]133;A`a")
    [Console]::Out.Write("`e]7;file://$hostName$cwd`a")
    return "PS $cwd> "
}
if (Get-Module -ListAvailable -Name PSReadLine) {
    Import-Module PSReadLine
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
        if ($line) {
            [Console]::Out.Write("`e]133;E;$line`a")
        }
        [Console]::Out.Write("`e]133;B`a")
        [Console]::Out.Write("`e]133;C`a")
        [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
    }
}
[Console]::Out.Write("`e]133;A`a")
"#;

/// Temporary shell bootstrap artifacts that must remain alive for the shell lifetime.
pub enum ShellBootstrap {
    /// Bash rcfile wrapper.
    Bash(NamedTempFile),
    /// Zsh dotfiles directory wrapper.
    Zsh(TempDir),
    /// Fish XDG config directory wrapper.
    Fish(TempDir),
    /// PowerShell profile wrapper.
    PowerShell(NamedTempFile),
    /// WSL bash rcfile wrapper.
    Wsl(NamedTempFile),
}

/// Prepare shell bootstrap files and mutate the shell config to use them.
pub fn prepare_shell_bootstrap(
    shell: &ShellType,
    config: &mut PtyConfig,
) -> Result<ShellBootstrap, std::io::Error> {
    match shell {
        ShellType::Bash => prepare_bash_bootstrap(config),
        ShellType::Zsh => prepare_zsh_bootstrap(config),
        ShellType::Fish => prepare_fish_bootstrap(config),
        ShellType::PowerShell => prepare_powershell_bootstrap(config),
        ShellType::Wsl(_) => prepare_wsl_bootstrap(config),
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

fn prepare_powershell_bootstrap(config: &mut PtyConfig) -> Result<ShellBootstrap, std::io::Error> {
    let mut profile = NamedTempFile::new()?;
    write!(profile, "{}", powershell_profile_script())?;

    config.args = vec![
        "-NoLogo".to_string(),
        "-NoProfile".to_string(),
        "-NoExit".to_string(),
        "-File".to_string(),
        profile.path().to_string_lossy().into_owned(),
    ];

    Ok(ShellBootstrap::PowerShell(profile))
}

/// Insert a WSL `--cd` argument before the command delimiter when a startup cwd is known.
pub fn apply_wsl_cwd(config: &mut PtyConfig, cwd: &Path) {
    if config.args.iter().any(|arg| arg == "--cd") {
        return;
    }

    if let Some(delimiter_index) = config.args.iter().position(|arg| arg == "--") {
        let translated = host_path_to_wsl(cwd);
        config.args.insert(delimiter_index, translated);
        config.args.insert(delimiter_index, "--cd".to_string());
    }
}

fn prepare_wsl_bootstrap(config: &mut PtyConfig) -> Result<ShellBootstrap, std::io::Error> {
    let mut rcfile = NamedTempFile::new()?;
    write!(
        rcfile,
        "\
# Walk shell bootstrap (wsl bash)
if [ -f \"$HOME/.bash_profile\" ]; then
    . \"$HOME/.bash_profile\"
elif [ -f \"$HOME/.bash_login\" ]; then
    . \"$HOME/.bash_login\"
elif [ -f \"$HOME/.profile\" ]; then
    . \"$HOME/.profile\"
fi
if [ -f \"$HOME/.bashrc\" ]; then
    . \"$HOME/.bashrc\"
fi
{BASH_INTEGRATION}
"
    )?;

    if let Some(index) = config.args.iter().position(|arg| arg == "bash") {
        config.args.splice(
            index + 1..,
            [
                "--noprofile".to_string(),
                "--norc".to_string(),
                "--rcfile".to_string(),
                host_path_to_wsl(rcfile.path()),
                "-i".to_string(),
            ],
        );
    }

    Ok(ShellBootstrap::Wsl(rcfile))
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

fn powershell_profile_script() -> String {
    format!(
        r#"
$walkProfiles = @()
if ($PROFILE) {{
    $walkProfiles += $PROFILE
    foreach ($name in @("AllUsersAllHosts", "AllUsersCurrentHost", "CurrentUserAllHosts", "CurrentUserCurrentHost")) {{
        $property = $PROFILE.PSObject.Properties[$name]
        if ($property -and $property.Value) {{
            $walkProfiles += $property.Value
        }}
    }}
}}

$walkProfiles |
    Where-Object {{ $_ }} |
    Select-Object -Unique |
    ForEach-Object {{
        if (Test-Path $_) {{
            . $_
        }}
    }}

{POWERSHELL_INTEGRATION}
"#
    )
}

fn host_path_to_wsl(path: &Path) -> String {
    let path_string = path.to_string_lossy();
    if cfg!(windows) {
        let normalized = path_string.replace('\\', "/");
        let mut chars = normalized.chars();
        if let (Some(drive), Some(':')) = (chars.next(), chars.next()) {
            let remainder = chars.as_str().trim_start_matches('/');
            return format!("/mnt/{}/{}", drive.to_ascii_lowercase(), remainder);
        }
        normalized
    } else {
        path_string.into_owned()
    }
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
        assert!(BASH_INTEGRATION.contains("133;E"));
        assert!(BASH_INTEGRATION.contains("133;B"));
        assert!(BASH_INTEGRATION.contains("133;C"));
        assert!(BASH_INTEGRATION.contains("133;D"));
    }

    #[test]
    fn test_zsh_integration_has_osc_markers() {
        assert!(ZSH_INTEGRATION.contains("133;A"));
        assert!(ZSH_INTEGRATION.contains("133;E"));
        assert!(ZSH_INTEGRATION.contains("133;B"));
        assert!(ZSH_INTEGRATION.contains("133;C"));
        assert!(ZSH_INTEGRATION.contains("133;D"));
    }

    #[test]
    fn test_fish_integration_has_osc_markers() {
        assert!(FISH_INTEGRATION.contains("133;A"));
        assert!(FISH_INTEGRATION.contains("133;E"));
        assert!(FISH_INTEGRATION.contains("133;B"));
        assert!(FISH_INTEGRATION.contains("133;C"));
        assert!(FISH_INTEGRATION.contains("133;D"));
    }

    #[test]
    fn test_powershell_integration_has_osc_markers() {
        assert!(POWERSHELL_INTEGRATION.contains("133;A"));
        assert!(POWERSHELL_INTEGRATION.contains("133;E"));
        assert!(POWERSHELL_INTEGRATION.contains("133;B"));
        assert!(POWERSHELL_INTEGRATION.contains("133;C"));
        assert!(POWERSHELL_INTEGRATION.contains("133;D"));
    }

    #[test]
    fn test_prepare_bash_bootstrap_sets_rcfile() {
        let mut config = test_config("bash");
        let bootstrap = prepare_shell_bootstrap(&ShellType::Bash, &mut config).unwrap();
        assert!(matches!(bootstrap, ShellBootstrap::Bash(_)));
        assert!(config.args.iter().any(|arg| arg == "--rcfile"));
    }

    #[test]
    fn test_prepare_zsh_bootstrap_sets_zdotdir() {
        let mut config = test_config("zsh");
        let bootstrap = prepare_shell_bootstrap(&ShellType::Zsh, &mut config).unwrap();
        assert!(matches!(bootstrap, ShellBootstrap::Zsh(_)));
        assert!(config.env.contains_key("ZDOTDIR"));
    }

    #[test]
    fn test_prepare_fish_bootstrap_sets_xdg_config_home() {
        let mut config = test_config("fish");
        let bootstrap = prepare_shell_bootstrap(&ShellType::Fish, &mut config).unwrap();
        assert!(matches!(bootstrap, ShellBootstrap::Fish(_)));
        assert!(config.env.contains_key("XDG_CONFIG_HOME"));
    }

    #[test]
    fn test_prepare_powershell_bootstrap_sets_file() {
        let mut config = test_config("pwsh");
        let bootstrap = prepare_shell_bootstrap(&ShellType::PowerShell, &mut config).unwrap();
        assert!(matches!(bootstrap, ShellBootstrap::PowerShell(_)));
        assert!(config.args.iter().any(|arg| arg == "-NoProfile"));
        assert!(config.args.iter().any(|arg| arg == "-File"));
        let ShellBootstrap::PowerShell(profile) = bootstrap else {
            panic!("expected powershell bootstrap");
        };
        let contents = fs::read_to_string(profile.path()).unwrap();
        assert!(contents.contains("$PROFILE"));
        assert!(contents.contains("Select-Object -Unique"));
        assert!(contents.contains("Set-PSReadLineKeyHandler"));
    }

    #[test]
    fn test_prepare_wsl_bootstrap_sets_rcfile() {
        let mut config = PtyConfig {
            shell: "wsl.exe".to_string(),
            args: vec![
                "-d".to_string(),
                "Ubuntu".to_string(),
                "--".to_string(),
                "bash".to_string(),
                "--login".to_string(),
            ],
            env: HashMap::new(),
        };
        let bootstrap =
            prepare_shell_bootstrap(&ShellType::Wsl("Ubuntu".to_string()), &mut config).unwrap();
        assert!(matches!(bootstrap, ShellBootstrap::Wsl(_)));
        assert!(config.args.iter().any(|arg| arg == "--rcfile"));
        assert_eq!(config.args[0], "-d");
        assert_eq!(config.args[1], "Ubuntu");
    }

    #[test]
    fn test_apply_wsl_cwd_inserts_cd_before_command_delimiter() {
        let mut config = PtyConfig {
            shell: "wsl.exe".to_string(),
            args: vec![
                "-d".to_string(),
                "Ubuntu".to_string(),
                "--".to_string(),
                "bash".to_string(),
                "--login".to_string(),
            ],
            env: HashMap::new(),
        };

        apply_wsl_cwd(&mut config, Path::new("/tmp/project"));

        let delimiter = config.args.iter().position(|arg| arg == "--").unwrap();
        assert_eq!(config.args[delimiter - 2], "--cd");
        assert_eq!(
            config.args[delimiter - 1],
            host_path_to_wsl(Path::new("/tmp/project"))
        );
        assert_eq!(config.args[delimiter + 1], "bash");
    }
}
