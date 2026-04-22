use std::collections::HashMap;
use std::error::Error;
use std::fs;
use std::io;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use wok_app::config::WokConfig;

const CONFIG_TEMPLATE: &str = r#"# Wok configuration
# See docs/CONFIGURATION.md for all options.
shell = "zsh"
font_family = "JetBrains Mono"
font_size = 24.0
scrollback_lines = 10000
input_position = "bottom"
tab_bar_orientation = "horizontal"
tab_bar_side = "top"
status_bar_visible = true
status_bar_side = "bottom"
recent_keys_visible = true
recent_keys_position = "bottom_right"
recent_keys_max_entries = 8
recent_keys_timeout_ms = 2000
recent_keys_opacity = 0.86
copy_on_select = false
close_on_shell_exit = true
restore_session = true
debug_overlay = false
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
const FIRST_RUN_MARKER_FILE: &str = ".first_run_complete";
const SHELL_INSTALL_MARKER_START: &str = "# >>> wok shell integration >>>";
const SHELL_INSTALL_MARKER_END: &str = "# <<< wok shell integration <<<";
const SHELL_INSTALL_STATE_FILE: &str = "install_state.json";

#[derive(Default)]
struct InitStats {
    created: Vec<PathBuf>,
    updated: Vec<PathBuf>,
    skipped: Vec<PathBuf>,
}

#[derive(Clone, Copy)]
enum CheckStatus {
    Ok,
    Warn,
    Fail,
}

impl CheckStatus {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Ok => "ok",
            Self::Warn => "warn",
            Self::Fail => "fail",
        }
    }
}

struct DoctorCheck {
    label: String,
    status: CheckStatus,
    detail: String,
}

#[derive(serde::Serialize)]
struct DoctorSummary {
    ok: usize,
    warn: usize,
    fail: usize,
}

#[derive(serde::Serialize)]
struct DoctorCheckView {
    label: String,
    status: String,
    detail: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ShellTarget {
    Bash,
    Zsh,
    Fish,
}

impl ShellTarget {
    fn as_str(self) -> &'static str {
        match self {
            Self::Bash => "bash",
            Self::Zsh => "zsh",
            Self::Fish => "fish",
        }
    }
}

#[derive(Debug, Default, serde::Serialize, serde::Deserialize)]
struct ShellInstallState {
    installs: HashMap<String, ShellInstallEntry>,
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
struct ShellInstallEntry {
    installed_at_ms: u64,
    records: Vec<ShellInstallRecord>,
}

#[derive(Debug, serde::Deserialize)]
#[serde(untagged)]
enum ShellInstallStateFile {
    Current(ShellInstallState),
    Legacy(LegacyShellInstallState),
}

#[derive(Debug, serde::Deserialize)]
struct LegacyShellInstallState {
    shell: String,
    installed_at_ms: u64,
    records: Vec<ShellInstallRecord>,
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
struct ShellInstallRecord {
    target_path: PathBuf,
    backup_path: Option<PathBuf>,
    created_new: bool,
}

#[derive(Debug, Clone, Copy, clap::ValueEnum)]
pub(crate) enum ResetScope {
    Managed,
    State,
    All,
}

pub(crate) fn run_init(overwrite: bool) -> Result<(), Box<dyn Error>> {
    let config_dir = WokConfig::config_dir();
    let stats = init_at(&config_dir, overwrite)?;
    write_first_run_marker(&config_dir)?;
    println!("Initialized Wok managed files at {}", config_dir.display());
    print_stats(&stats);
    println!("Run `wok doctor` to verify setup.");
    Ok(())
}

pub(crate) fn ensure_first_run_bootstrap() -> Result<Option<String>, Box<dyn Error>> {
    let config_dir = WokConfig::config_dir();
    let result = ensure_first_run_bootstrap_at(&config_dir)?;
    Ok(result)
}

pub(crate) fn run_doctor(as_json: bool) -> Result<(), Box<dyn Error>> {
    let config_dir = WokConfig::config_dir();
    let checks = doctor_checks_at(&config_dir);
    let summary = doctor_summary(&checks);

    if as_json {
        let output = serde_json::json!({
            "config_dir": config_dir,
            "checks": checks
                .iter()
                .map(|check| DoctorCheckView {
                    label: check.label.clone(),
                    status: check.status.as_str().to_string(),
                    detail: check.detail.clone(),
                })
                .collect::<Vec<_>>(),
            "summary": summary,
        });
        println!("{}", serde_json::to_string_pretty(&output)?);
    } else {
        println!("Wok doctor");
        println!("config_dir: {}", config_dir.display());
        for check in &checks {
            println!(
                "[{}] {}: {}",
                check.status.as_str(),
                check.label,
                check.detail
            );
        }
        println!(
            "summary: {} ok, {} warning, {} failed",
            summary.ok, summary.warn, summary.fail
        );
    }

    if summary.fail > 0 {
        return Err("doctor found failing checks".into());
    }
    Ok(())
}

pub(crate) fn run_reset(scope: ResetScope, yes: bool) -> Result<(), Box<dyn Error>> {
    if !yes {
        return Err("reset is destructive; re-run with `wok reset --yes`".into());
    }
    let config_dir = WokConfig::config_dir();
    let stats = reset_at(&config_dir, scope)?;
    println!("Reset Wok managed files at {}", config_dir.display());
    for path in &stats.removed {
        println!("removed {}", path.display());
    }
    for path in &stats.missing {
        println!("absent  {}", path.display());
    }
    Ok(())
}

pub(crate) fn run_shell_install(
    shell_arg: Option<&str>,
    overwrite: bool,
) -> Result<(), Box<dyn Error>> {
    let config_dir = WokConfig::config_dir();
    init_at(&config_dir, overwrite)?;

    let shell = resolve_shell_target(shell_arg)?;
    let target_path = shell_startup_path(shell)?;
    let mut record = prepare_install_target(&target_path)?;
    let source_script = config_dir.join("shell").join(shell_script_file(shell));
    let block = integration_block(shell, &source_script);
    let existing = fs::read_to_string(&target_path).unwrap_or_default();
    let updated = replace_or_append_managed_block(&existing, &block);
    fs::write(&target_path, updated)?;
    record.target_path = target_path.clone();
    set_executable_if_script(&target_path)?;

    let shell_name = shell.as_str().to_string();
    let mut state = load_shell_install_state(&config_dir)?.unwrap_or_default();
    let previous = state.installs.insert(
        shell_name.clone(),
        ShellInstallEntry {
            installed_at_ms: unix_time_ms_now(),
            records: vec![record],
        },
    );
    if let Some(previous) = previous {
        cleanup_shell_install_entry_backups(&previous);
    }
    save_shell_install_state(&config_dir, &state)?;

    println!(
        "Installed Wok shell wiring for {} at {}",
        shell.as_str(),
        target_path.display()
    );
    println!(
        "Run `wok shell rollback --shell {} --yes` to restore the previous file.",
        shell.as_str()
    );
    Ok(())
}

pub(crate) fn run_shell_rollback(shell_arg: Option<&str>, yes: bool) -> Result<(), Box<dyn Error>> {
    if !yes {
        return Err("rollback is destructive; re-run with `wok shell rollback --yes`".into());
    }
    let config_dir = WokConfig::config_dir();
    let mut state = load_shell_install_state(&config_dir)?
        .ok_or("no shell install state found; nothing to roll back")?;
    let shell = resolve_shell_rollback_target(shell_arg, &state)?;
    let entry = state
        .installs
        .remove(&shell)
        .ok_or_else(|| format!("no install state found for shell '{shell}'"))?;

    for record in &entry.records {
        rollback_record(record)?;
    }

    let state_path = shell_install_state_path(&config_dir);
    if state.installs.is_empty() {
        if state_path.exists() {
            fs::remove_file(&state_path)?;
        }
    } else {
        save_shell_install_state(&config_dir, &state)?;
    }
    println!("Rolled back shell wiring for {}", shell);
    Ok(())
}

fn resolve_shell_rollback_target(
    shell_arg: Option<&str>,
    state: &ShellInstallState,
) -> Result<String, Box<dyn Error>> {
    if let Some(shell) = shell_arg.map(str::trim).filter(|value| !value.is_empty()) {
        let parsed = parse_shell_target(shell).ok_or_else(|| {
            format!("unsupported shell '{shell}'. expected one of: bash, zsh, fish")
        })?;
        return Ok(parsed.as_str().to_string());
    }

    let mut installed = state.installs.keys().cloned().collect::<Vec<_>>();
    installed.sort();
    if installed.len() == 1 {
        return Ok(installed.remove(0));
    }
    if installed.is_empty() {
        return Err("no shell install state found; nothing to roll back".into());
    }
    Err(format!(
        "multiple shell installs found ({}); rerun with `--shell <bash|zsh|fish>`",
        installed.join(", ")
    )
    .into())
}

fn cleanup_shell_install_entry_backups(entry: &ShellInstallEntry) {
    for record in &entry.records {
        if let Some(backup) = &record.backup_path {
            if backup.exists() {
                let _ = fs::remove_file(backup);
            }
        }
    }
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

fn resolve_shell_target(shell_arg: Option<&str>) -> Result<ShellTarget, Box<dyn Error>> {
    if let Some(shell) = shell_arg.map(str::trim).filter(|value| !value.is_empty()) {
        if shell.eq_ignore_ascii_case("auto") {
            return resolve_shell_target(None);
        }
        return parse_shell_target(shell).ok_or_else(|| {
            format!("unsupported shell '{shell}'. expected one of: auto, bash, zsh, fish").into()
        });
    }

    let default_shell = WokConfig::load().shell.to_string();
    if let Some(target) = parse_shell_target(&default_shell) {
        return Ok(target);
    }
    Ok(ShellTarget::Bash)
}

fn parse_shell_target(value: &str) -> Option<ShellTarget> {
    match value.to_ascii_lowercase().as_str() {
        "auto" => None,
        "bash" => Some(ShellTarget::Bash),
        "zsh" => Some(ShellTarget::Zsh),
        "fish" => Some(ShellTarget::Fish),
        _ => None,
    }
}

fn shell_script_file(shell: ShellTarget) -> &'static str {
    match shell {
        ShellTarget::Bash => "bash.sh",
        ShellTarget::Zsh => "zsh.zsh",
        ShellTarget::Fish => "fish.fish",
    }
}

fn shell_startup_path(shell: ShellTarget) -> Result<PathBuf, Box<dyn Error>> {
    let home = std::env::var("HOME")
        .map(PathBuf::from)
        .map_err(|_| "HOME is not set; cannot resolve shell startup file")?;
    let path = match shell {
        ShellTarget::Bash => home.join(".bashrc"),
        ShellTarget::Zsh => home.join(".zshrc"),
        ShellTarget::Fish => home
            .join(".config")
            .join("fish")
            .join("conf.d")
            .join("wok.fish"),
    };
    Ok(path)
}

fn integration_block(shell: ShellTarget, source_script: &Path) -> String {
    match shell {
        ShellTarget::Fish => format!(
            "{SHELL_INSTALL_MARKER_START}\nif test -f \"{}\"\n    source \"{}\"\nend\n{SHELL_INSTALL_MARKER_END}\n",
            source_script.display(),
            source_script.display()
        ),
        ShellTarget::Bash | ShellTarget::Zsh => format!(
            "{SHELL_INSTALL_MARKER_START}\nif [ -f \"{}\" ]; then\n  source \"{}\"\nfi\n{SHELL_INSTALL_MARKER_END}\n",
            source_script.display(),
            source_script.display()
        ),
    }
}

fn prepare_install_target(path: &Path) -> io::Result<ShellInstallRecord> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    if path.exists() {
        let backup_path = backup_path_for(path);
        fs::copy(path, &backup_path)?;
        return Ok(ShellInstallRecord {
            target_path: path.to_path_buf(),
            backup_path: Some(backup_path),
            created_new: false,
        });
    }
    fs::write(path, "")?;
    Ok(ShellInstallRecord {
        target_path: path.to_path_buf(),
        backup_path: None,
        created_new: true,
    })
}

fn backup_path_for(path: &Path) -> PathBuf {
    let mut backup = path.as_os_str().to_os_string();
    backup.push(".wok.bak");
    PathBuf::from(backup)
}

fn replace_or_append_managed_block(existing: &str, block: &str) -> String {
    let start = existing.find(SHELL_INSTALL_MARKER_START);
    let end = existing.find(SHELL_INSTALL_MARKER_END);
    if let Some(start_index) = start {
        let mut out = String::new();
        out.push_str(&existing[..start_index]);
        out.push_str(block);
        if let Some(end_index) = end.filter(|index| *index >= start_index) {
            let end_line = end_index + SHELL_INSTALL_MARKER_END.len();
            out.push_str(existing[end_line..].trim_start_matches('\n'));
        }
        if !out.ends_with('\n') {
            out.push('\n');
        }
        return out;
    }

    if let Some(end_index) = end {
        let end_line = end_index + SHELL_INSTALL_MARKER_END.len();
        let mut out = existing[end_line..].trim_start_matches('\n').to_string();
        if !out.is_empty() && !out.ends_with('\n') {
            out.push('\n');
        }
        out.push_str(block);
        return out;
    }

    let mut out = existing.to_string();
    if !out.is_empty() && !out.ends_with('\n') {
        out.push('\n');
    }
    out.push_str(block);
    out
}

fn remove_managed_block(existing: &str) -> String {
    let start = existing.find(SHELL_INSTALL_MARKER_START);
    let end = existing.find(SHELL_INSTALL_MARKER_END);

    if let Some(start_index) = start {
        let mut out = String::new();
        out.push_str(&existing[..start_index]);
        if let Some(end_index) = end.filter(|index| *index >= start_index) {
            let end_line = end_index + SHELL_INSTALL_MARKER_END.len();
            out.push_str(existing[end_line..].trim_start_matches('\n'));
        }
        if out.trim().is_empty() {
            return String::new();
        }
        let mut out = out.trim_end().to_string();
        out.push('\n');
        return out;
    }

    if let Some(end_index) = end {
        let end_line = end_index + SHELL_INSTALL_MARKER_END.len();
        let out = existing[end_line..].trim_start_matches('\n').trim_end();
        if out.is_empty() {
            return String::new();
        }
        return format!("{out}\n");
    }

    existing.to_string()
}

fn set_executable_if_script(path: &Path) -> io::Result<()> {
    let ext = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("");
    if ext == "sh" || ext == "zsh" || ext == "fish" {
        set_executable(path)?;
    }
    Ok(())
}

fn shell_install_state_path(config_dir: &Path) -> PathBuf {
    config_dir.join("shell").join(SHELL_INSTALL_STATE_FILE)
}

fn save_shell_install_state(config_dir: &Path, state: &ShellInstallState) -> io::Result<()> {
    let path = shell_install_state_path(config_dir);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let payload = serde_json::to_string_pretty(state)
        .map_err(|error| io::Error::other(format!("failed to serialize state: {error}")))?;
    fs::write(path, payload)
}

fn load_shell_install_state(config_dir: &Path) -> io::Result<Option<ShellInstallState>> {
    let path = shell_install_state_path(config_dir);
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(path)?;
    let parsed = serde_json::from_str::<ShellInstallStateFile>(&content)
        .map_err(|error| io::Error::other(format!("failed to parse install state: {error}")))?;
    let state = match parsed {
        ShellInstallStateFile::Current(current) => current,
        ShellInstallStateFile::Legacy(legacy) => {
            let mut installs = HashMap::new();
            installs.insert(
                legacy.shell,
                ShellInstallEntry {
                    installed_at_ms: legacy.installed_at_ms,
                    records: legacy.records,
                },
            );
            ShellInstallState { installs }
        }
    };
    Ok(Some(state))
}

fn rollback_record(record: &ShellInstallRecord) -> io::Result<()> {
    if let Some(backup_path) = &record.backup_path {
        if backup_path.exists() {
            fs::copy(backup_path, &record.target_path)?;
            return Ok(());
        }
    }

    if !record.target_path.exists() {
        return Ok(());
    }
    let existing = fs::read_to_string(&record.target_path).unwrap_or_default();
    let updated = remove_managed_block(&existing);
    if record.created_new && updated.trim().is_empty() {
        fs::remove_file(&record.target_path)?;
        return Ok(());
    }
    fs::write(&record.target_path, updated)
}

fn unix_time_ms_now() -> u64 {
    unix_time_ms(SystemTime::now())
}

fn unix_time_ms(time: SystemTime) -> u64 {
    time.duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
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

    let marker_path = config_dir.join(FIRST_RUN_MARKER_FILE);
    checks.push(DoctorCheck {
        label: FIRST_RUN_MARKER_FILE.to_string(),
        status: if marker_path.exists() {
            CheckStatus::Ok
        } else {
            CheckStatus::Warn
        },
        detail: if marker_path.exists() {
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

fn doctor_summary(checks: &[DoctorCheck]) -> DoctorSummary {
    let mut summary = DoctorSummary {
        ok: 0,
        warn: 0,
        fail: 0,
    };
    for check in checks {
        match check.status {
            CheckStatus::Ok => summary.ok += 1,
            CheckStatus::Warn => summary.warn += 1,
            CheckStatus::Fail => summary.fail += 1,
        }
    }
    summary
}

#[derive(Default)]
struct ResetStats {
    removed: Vec<PathBuf>,
    missing: Vec<PathBuf>,
}

fn reset_at(config_dir: &Path, scope: ResetScope) -> io::Result<ResetStats> {
    let mut stats = ResetStats::default();
    let mut remove_targets = Vec::new();
    if matches!(scope, ResetScope::Managed | ResetScope::All) {
        remove_targets.extend([
            config_dir.join("config.toml"),
            config_dir.join("init.lua"),
            config_dir.join(FIRST_RUN_MARKER_FILE),
            config_dir.join("shell").join("bash.sh"),
            config_dir.join("shell").join("zsh.zsh"),
            config_dir.join("shell").join("fish.fish"),
            config_dir.join("shell").join(SHELL_INSTALL_STATE_FILE),
        ]);
    }
    if matches!(scope, ResetScope::State | ResetScope::All) {
        remove_targets.extend([
            config_dir.join("session.json"),
            config_dir.join("sessions"),
            config_dir.join("themes"),
            config_dir.join("workflows"),
        ]);
    }

    for path in remove_targets {
        remove_path(path, &mut stats)?;
    }

    // Attempt to clean up empty shell dir after managed file removals.
    if matches!(scope, ResetScope::Managed | ResetScope::All) {
        let shell_dir = config_dir.join("shell");
        if shell_dir.exists() && shell_dir.read_dir()?.next().is_none() {
            remove_path(shell_dir, &mut stats)?;
        }
    }

    Ok(stats)
}

fn ensure_first_run_bootstrap_at(config_dir: &Path) -> io::Result<Option<String>> {
    let marker = config_dir.join(FIRST_RUN_MARKER_FILE);
    if marker.exists() {
        return Ok(None);
    }

    let stats = init_at(config_dir, false)?;
    write_first_run_marker(config_dir)?;

    let created_count = stats.created.len();
    let message = if created_count == 0 {
        "Wok first-run setup complete".to_string()
    } else {
        format!("Wok first-run setup complete ({created_count} files)")
    };
    Ok(Some(message))
}

fn write_first_run_marker(config_dir: &Path) -> io::Result<()> {
    fs::create_dir_all(config_dir)?;
    fs::write(
        config_dir.join(FIRST_RUN_MARKER_FILE),
        "managed by wok init/first-run bootstrap\n",
    )
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

        let stats = reset_at(&dir, ResetScope::Managed).expect("reset should succeed");
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

        let _stats = reset_at(&dir, ResetScope::All).expect("reset should succeed");
        assert!(!dir.join("session.json").exists());
        assert!(!dir.join("sessions").exists());
        assert!(!dir.join("themes").exists());
        assert!(!dir.join("workflows").exists());

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn test_first_run_bootstrap_creates_marker() {
        let dir = unique_temp_dir();
        let message = ensure_first_run_bootstrap_at(&dir).expect("bootstrap should succeed");

        assert!(message.is_some());
        assert!(dir.join(FIRST_RUN_MARKER_FILE).exists());
        assert!(dir.join("config.toml").exists());
        assert!(dir.join("init.lua").exists());

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn test_first_run_bootstrap_is_idempotent_after_marker_exists() {
        let dir = unique_temp_dir();
        fs::create_dir_all(&dir).expect("temp dir should be created");
        fs::write(dir.join(FIRST_RUN_MARKER_FILE), "done").expect("marker should be written");

        let message = ensure_first_run_bootstrap_at(&dir).expect("bootstrap should succeed");
        assert!(message.is_none());
    }

    #[test]
    fn test_replace_or_append_managed_block_replaces_existing_marked_section() {
        let existing = format!(
            "export PATH=$PATH\n{SHELL_INSTALL_MARKER_START}\nold\n{SHELL_INSTALL_MARKER_END}\n"
        );
        let replaced = replace_or_append_managed_block(&existing, "new-block\n");
        assert!(replaced.contains("new-block"));
        assert!(!replaced.contains("\nold\n"));
    }

    #[test]
    fn test_replace_or_append_managed_block_handles_missing_end_marker() {
        let existing = format!("line1\n{SHELL_INSTALL_MARKER_START}\nline2\n");
        let replaced = replace_or_append_managed_block(&existing, "new-block\n");
        assert!(replaced.contains("new-block"));
        assert!(!replaced.contains("line2"));
    }

    #[test]
    fn test_remove_managed_block_strips_marker_block() {
        let existing = format!(
            "line1\n{SHELL_INSTALL_MARKER_START}\nline2\n{SHELL_INSTALL_MARKER_END}\nline3\n"
        );
        let updated = remove_managed_block(&existing);
        assert!(updated.contains("line1"));
        assert!(updated.contains("line3"));
        assert!(!updated.contains(SHELL_INSTALL_MARKER_START));
    }

    #[test]
    fn test_remove_managed_block_handles_missing_end_marker() {
        let existing = format!("line1\n{SHELL_INSTALL_MARKER_START}\nline2\n");
        let updated = remove_managed_block(&existing);
        assert_eq!(updated, "line1\n");
    }

    #[test]
    fn test_rollback_record_restores_backup() {
        let dir = unique_temp_dir();
        fs::create_dir_all(&dir).expect("temp dir should be created");
        let target = dir.join(".zshrc");
        fs::write(&target, "before\n").expect("target should be written");
        let backup = backup_path_for(&target);
        fs::copy(&target, &backup).expect("backup should be copied");
        fs::write(&target, "after\n").expect("target should be updated");

        let record = ShellInstallRecord {
            target_path: target.clone(),
            backup_path: Some(backup.clone()),
            created_new: false,
        };
        rollback_record(&record).expect("rollback should succeed");

        let restored = fs::read_to_string(&target).expect("target should be readable");
        assert_eq!(restored, "before\n");
    }

    #[test]
    fn test_load_shell_install_state_supports_legacy_format() {
        let dir = unique_temp_dir();
        fs::create_dir_all(dir.join("shell")).expect("shell dir should be created");
        fs::write(
            dir.join("shell").join(SHELL_INSTALL_STATE_FILE),
            r#"{
  "shell": "zsh",
  "installed_at_ms": 123,
  "records": [
    {"target_path":"/tmp/.zshrc","backup_path":null,"created_new":false}
  ]
}"#,
        )
        .expect("legacy state should be written");

        let state = load_shell_install_state(&dir)
            .expect("state load should succeed")
            .expect("state should exist");
        assert!(state.installs.contains_key("zsh"));
        assert_eq!(state.installs.get("zsh").unwrap().installed_at_ms, 123);
    }

    #[test]
    fn test_save_shell_install_state_round_trips_multiple_shells() {
        let dir = unique_temp_dir();
        let mut state = ShellInstallState::default();
        state.installs.insert(
            "bash".to_string(),
            ShellInstallEntry {
                installed_at_ms: 1,
                records: vec![ShellInstallRecord {
                    target_path: PathBuf::from("/tmp/.bashrc"),
                    backup_path: None,
                    created_new: false,
                }],
            },
        );
        state.installs.insert(
            "zsh".to_string(),
            ShellInstallEntry {
                installed_at_ms: 2,
                records: vec![ShellInstallRecord {
                    target_path: PathBuf::from("/tmp/.zshrc"),
                    backup_path: Some(PathBuf::from("/tmp/.zshrc.wok.bak")),
                    created_new: false,
                }],
            },
        );

        save_shell_install_state(&dir, &state).expect("state should save");
        let loaded = load_shell_install_state(&dir)
            .expect("state should load")
            .expect("state should exist");
        assert_eq!(loaded.installs.len(), 2);
        assert!(loaded.installs.contains_key("bash"));
        assert!(loaded.installs.contains_key("zsh"));
    }
}
