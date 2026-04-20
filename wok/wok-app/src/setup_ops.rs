use std::error::Error;
use std::fs;
use std::io;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use wok_app::config::WokConfig;

const CONFIG_TEMPLATE: &str = r#"# Wok configuration
# See docs/CONFIGURATION.md for all options.
shell = "zsh"
font_family = "JetBrains Mono"
font_size = 14.0
scrollback_lines = 10000
copy_on_select = false
restore_session = true
"#;

const LUA_TEMPLATE: &str = r#"-- Wok init.lua
-- See docs/LUA_SCRIPTING.md for all APIs.

wok.on("app_start", function()
    wok.notify("Wok ready")
end)
"#;

const BASH_SCRIPT: &str = include_str!("../../shell-integration/bash.sh");
const ZSH_SCRIPT: &str = include_str!("../../shell-integration/zsh.zsh");
const FISH_SCRIPT: &str = include_str!("../../shell-integration/fish.fish");

#[derive(Default)]
struct InitStats {
    created: Vec<PathBuf>,
    updated: Vec<PathBuf>,
    skipped: Vec<PathBuf>,
}

enum CheckStatus {
    Ok,
    Warn,
    Fail,
}

struct DoctorCheck {
    label: String,
    status: CheckStatus,
    detail: String,
}

pub(crate) fn run_init(overwrite: bool) -> Result<(), Box<dyn Error>> {
    let config_dir = WokConfig::config_dir();
    let stats = init_at(&config_dir, overwrite)?;
    println!("Initialized Wok managed files at {}", config_dir.display());
    print_stats(&stats);
    println!("Run `wok doctor` to verify setup.");
    Ok(())
}

pub(crate) fn run_doctor() -> Result<(), Box<dyn Error>> {
    let config_dir = WokConfig::config_dir();
    let checks = doctor_checks_at(&config_dir);

    println!("Wok doctor");
    println!("config_dir: {}", config_dir.display());

    let mut ok_count = 0usize;
    let mut warn_count = 0usize;
    let mut fail_count = 0usize;
    for check in checks {
        let status = match check.status {
            CheckStatus::Ok => {
                ok_count += 1;
                "ok"
            }
            CheckStatus::Warn => {
                warn_count += 1;
                "warn"
            }
            CheckStatus::Fail => {
                fail_count += 1;
                "fail"
            }
        };
        println!("[{status}] {}: {}", check.label, check.detail);
    }

    println!("summary: {ok_count} ok, {warn_count} warning, {fail_count} failed");
    if fail_count > 0 {
        return Err("doctor found failing checks".into());
    }
    Ok(())
}

pub(crate) fn run_reset(all: bool, yes: bool) -> Result<(), Box<dyn Error>> {
    if !yes {
        return Err("reset is destructive; re-run with `wok reset --yes`".into());
    }
    let config_dir = WokConfig::config_dir();
    let stats = reset_at(&config_dir, all)?;
    println!("Reset Wok managed files at {}", config_dir.display());
    for path in &stats.removed {
        println!("removed {}", path.display());
    }
    for path in &stats.missing {
        println!("absent  {}", path.display());
    }
    Ok(())
}

fn print_stats(stats: &InitStats) {
    for path in &stats.created {
        println!("created {}", path.display());
    }
    for path in &stats.updated {
        println!("updated {}", path.display());
    }
    for path in &stats.skipped {
        println!("kept    {}", path.display());
    }
}

fn doctor_checks_at(config_dir: &Path) -> Vec<DoctorCheck> {
    let mut checks = Vec::new();
    let config_exists = config_dir.exists();
    checks.push(DoctorCheck {
        label: "config_dir".to_string(),
        status: if config_exists {
            CheckStatus::Ok
        } else {
            CheckStatus::Warn
        },
        detail: if config_exists {
            "exists".to_string()
        } else {
            "missing (run `wok init`)".to_string()
        },
    });

    let config_path = config_dir.join("config.toml");
    if !config_path.exists() {
        checks.push(DoctorCheck {
            label: "config.toml".to_string(),
            status: CheckStatus::Warn,
            detail: "missing".to_string(),
        });
    } else {
        match fs::read_to_string(&config_path) {
            Ok(content) => match toml::from_str::<toml::Value>(&content) {
                Ok(_) => checks.push(DoctorCheck {
                    label: "config.toml".to_string(),
                    status: CheckStatus::Ok,
                    detail: "parseable".to_string(),
                }),
                Err(error) => checks.push(DoctorCheck {
                    label: "config.toml".to_string(),
                    status: CheckStatus::Fail,
                    detail: format!("invalid TOML: {error}"),
                }),
            },
            Err(error) => checks.push(DoctorCheck {
                label: "config.toml".to_string(),
                status: CheckStatus::Fail,
                detail: format!("not readable: {error}"),
            }),
        }
    }

    let init_lua_path = config_dir.join("init.lua");
    checks.push(DoctorCheck {
        label: "init.lua".to_string(),
        status: if init_lua_path.exists() {
            CheckStatus::Ok
        } else {
            CheckStatus::Warn
        },
        detail: if init_lua_path.exists() {
            "present".to_string()
        } else {
            "missing".to_string()
        },
    });

    for name in ["bash.sh", "zsh.zsh", "fish.fish"] {
        let path = config_dir.join("shell").join(name);
        checks.push(DoctorCheck {
            label: format!("shell/{name}"),
            status: if path.exists() {
                CheckStatus::Ok
            } else {
                CheckStatus::Warn
            },
            detail: if path.exists() {
                "present".to_string()
            } else {
                "missing".to_string()
            },
        });
    }

    checks.push(DoctorCheck {
        label: "default_shell".to_string(),
        status: CheckStatus::Ok,
        detail: WokConfig::load().shell.to_string(),
    });

    checks
}

#[derive(Default)]
struct ResetStats {
    removed: Vec<PathBuf>,
    missing: Vec<PathBuf>,
}

fn reset_at(config_dir: &Path, all: bool) -> io::Result<ResetStats> {
    let mut stats = ResetStats::default();
    let mut remove_targets = vec![
        config_dir.join("config.toml"),
        config_dir.join("init.lua"),
        config_dir.join("shell").join("bash.sh"),
        config_dir.join("shell").join("zsh.zsh"),
        config_dir.join("shell").join("fish.fish"),
    ];
    if all {
        remove_targets.push(config_dir.join("session.json"));
        remove_targets.push(config_dir.join("sessions"));
        remove_targets.push(config_dir.join("themes"));
        remove_targets.push(config_dir.join("workflows"));
    }

    for path in remove_targets {
        remove_path(path, &mut stats)?;
    }

    // Attempt to clean up empty shell dir after script removals.
    let shell_dir = config_dir.join("shell");
    if shell_dir.exists() && shell_dir.read_dir()?.next().is_none() {
        remove_path(shell_dir, &mut stats)?;
    }

    Ok(stats)
}

fn remove_path(path: PathBuf, stats: &mut ResetStats) -> io::Result<()> {
    if !path.exists() {
        stats.missing.push(path);
        return Ok(());
    }

    let metadata = fs::metadata(&path)?;
    if metadata.is_dir() {
        fs::remove_dir_all(&path)?;
    } else {
        fs::remove_file(&path)?;
    }
    stats.removed.push(path);
    Ok(())
}

fn init_at(config_dir: &Path, overwrite: bool) -> io::Result<InitStats> {
    fs::create_dir_all(config_dir)?;
    fs::create_dir_all(config_dir.join("shell"))?;
    fs::create_dir_all(config_dir.join("themes"))?;
    fs::create_dir_all(config_dir.join("workflows"))?;
    fs::create_dir_all(config_dir.join("sessions"))?;

    let mut stats = InitStats::default();
    write_managed_file(
        config_dir.join("config.toml"),
        CONFIG_TEMPLATE,
        overwrite,
        false,
        &mut stats,
    )?;
    write_managed_file(
        config_dir.join("init.lua"),
        LUA_TEMPLATE,
        overwrite,
        false,
        &mut stats,
    )?;
    write_managed_file(
        config_dir.join("shell").join("bash.sh"),
        BASH_SCRIPT,
        overwrite,
        true,
        &mut stats,
    )?;
    write_managed_file(
        config_dir.join("shell").join("zsh.zsh"),
        ZSH_SCRIPT,
        overwrite,
        true,
        &mut stats,
    )?;
    write_managed_file(
        config_dir.join("shell").join("fish.fish"),
        FISH_SCRIPT,
        overwrite,
        true,
        &mut stats,
    )?;

    Ok(stats)
}

fn write_managed_file(
    path: PathBuf,
    content: &str,
    overwrite: bool,
    executable: bool,
    stats: &mut InitStats,
) -> io::Result<()> {
    if path.exists() && !overwrite {
        stats.skipped.push(path);
        return Ok(());
    }

    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    let existed = path.exists();
    fs::write(&path, content)?;
    if executable {
        set_executable(&path)?;
    }

    if existed {
        stats.updated.push(path);
    } else {
        stats.created.push(path);
    }
    Ok(())
}

#[cfg(unix)]
fn set_executable(path: &Path) -> io::Result<()> {
    let mut perms = fs::metadata(path)?.permissions();
    perms.set_mode(0o755);
    fs::set_permissions(path, perms)
}

#[cfg(not(unix))]
fn set_executable(_path: &Path) -> io::Result<()> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_temp_dir() -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time should move forward")
            .as_nanos();
        std::env::temp_dir().join(format!("wok-setup-{nanos}"))
    }

    #[test]
    fn test_init_creates_managed_files() {
        let dir = unique_temp_dir();
        let stats = init_at(&dir, false).expect("init should succeed");

        assert!(dir.join("config.toml").exists());
        assert!(dir.join("init.lua").exists());
        assert!(dir.join("shell").join("bash.sh").exists());
        assert!(dir.join("shell").join("zsh.zsh").exists());
        assert!(dir.join("shell").join("fish.fish").exists());
        assert!(!stats.created.is_empty());

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn test_init_without_overwrite_keeps_existing_file() {
        let dir = unique_temp_dir();
        fs::create_dir_all(&dir).expect("temp dir should be created");
        fs::write(dir.join("config.toml"), "font_size = 20.0\n")
            .expect("seed config should be written");

        let stats = init_at(&dir, false).expect("init should succeed");
        let config =
            fs::read_to_string(dir.join("config.toml")).expect("config should be readable");
        assert_eq!(config, "font_size = 20.0\n");
        assert!(stats
            .skipped
            .iter()
            .any(|path| path.ends_with("config.toml")));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn test_doctor_warns_when_not_initialized() {
        let dir = unique_temp_dir();
        let checks = doctor_checks_at(&dir);

        assert!(checks.iter().any(|check| {
            matches!(check.status, CheckStatus::Warn) && check.label == "config_dir"
        }));
    }

    #[test]
    fn test_doctor_reports_ok_after_init() {
        let dir = unique_temp_dir();
        init_at(&dir, false).expect("init should succeed");

        let checks = doctor_checks_at(&dir);
        assert!(checks.iter().any(|check| {
            matches!(check.status, CheckStatus::Ok) && check.label == "config.toml"
        }));
        assert!(checks.iter().any(|check| {
            matches!(check.status, CheckStatus::Ok) && check.label == "shell/bash.sh"
        }));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn test_reset_removes_managed_files() {
        let dir = unique_temp_dir();
        init_at(&dir, false).expect("init should succeed");

        let stats = reset_at(&dir, false).expect("reset should succeed");
        assert!(stats
            .removed
            .iter()
            .any(|path| path.ends_with("config.toml")));
        assert!(!dir.join("config.toml").exists());
        assert!(!dir.join("init.lua").exists());
        assert!(!dir.join("shell").exists());

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn test_reset_all_removes_session_state() {
        let dir = unique_temp_dir();
        init_at(&dir, false).expect("init should succeed");
        fs::write(dir.join("session.json"), "{}").expect("session file should be created");
        fs::create_dir_all(dir.join("sessions")).expect("sessions dir should be created");
        fs::write(dir.join("sessions").join("demo.json"), "{}")
            .expect("session snapshot should be created");

        let _stats = reset_at(&dir, true).expect("reset should succeed");
        assert!(!dir.join("session.json").exists());
        assert!(!dir.join("sessions").exists());
        assert!(!dir.join("themes").exists());
        assert!(!dir.join("workflows").exists());

        let _ = fs::remove_dir_all(dir);
    }
}
