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

pub(crate) fn run_init(overwrite: bool) -> Result<(), Box<dyn Error>> {
    let config_dir = WokConfig::config_dir();
    let stats = init_at(&config_dir, overwrite)?;
    println!("Initialized Wok managed files at {}", config_dir.display());
    print_stats(&stats);
    println!("Run `wok doctor` to verify setup.");
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
}
