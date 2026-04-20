#![cfg(unix)]

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

fn unique_home() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time should be after epoch")
        .as_nanos();
    std::env::temp_dir().join(format!("wok-cli-it-{}-{nanos}", std::process::id()))
}

fn run_wok(home: &Path, args: &[&str]) -> Output {
    let bin = std::env::var("CARGO_BIN_EXE_wok")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("target")
                .join("debug")
                .join("wok")
        });
    Command::new(bin)
        .args(args)
        .env("HOME", home)
        .env(
            "RUSTUP_HOME",
            std::env::var("RUSTUP_HOME").unwrap_or_else(|_| {
                format!(
                    "{}/.rustup",
                    std::env::var("HOME").expect("parent HOME should be available")
                )
            }),
        )
        .env(
            "CARGO_HOME",
            std::env::var("CARGO_HOME").unwrap_or_else(|_| {
                format!(
                    "{}/.cargo",
                    std::env::var("HOME").expect("parent HOME should be available")
                )
            }),
        )
        .output()
        .expect("wok command should execute")
}

fn config_dir(home: &Path) -> PathBuf {
    home.join(".config").join("wok")
}

fn assert_success(output: &Output) {
    assert!(
        output.status.success(),
        "command failed\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

fn assert_failure(output: &Output) {
    assert!(
        !output.status.success(),
        "command unexpectedly succeeded\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn init_doctor_and_reset_managed_lifecycle() {
    let home = unique_home();
    fs::create_dir_all(&home).expect("temp home should be created");

    let marker = config_dir(&home).join(".first_run_complete");
    assert!(!marker.exists(), "marker should not exist before setup");

    let doctor_before = run_wok(&home, &["doctor", "--json"]);
    assert_success(&doctor_before);
    assert!(
        !marker.exists(),
        "doctor should not create first-run marker by itself"
    );

    let init = run_wok(&home, &["init"]);
    assert_success(&init);
    assert!(marker.exists(), "init should create first-run marker");
    assert!(config_dir(&home).join("config.toml").exists());
    assert!(config_dir(&home).join("init.lua").exists());

    let doctor_after = run_wok(&home, &["doctor", "--json"]);
    assert_success(&doctor_after);
    let doctor_json: serde_json::Value =
        serde_json::from_slice(&doctor_after.stdout).expect("doctor json should parse");
    assert_eq!(doctor_json["summary"]["fail"].as_u64(), Some(0));

    let reset = run_wok(&home, &["reset", "--scope", "managed", "--yes"]);
    assert_success(&reset);
    assert!(!config_dir(&home).join("config.toml").exists());
    assert!(!config_dir(&home).join("init.lua").exists());
    assert!(!marker.exists());
}

#[test]
fn reset_state_preserves_managed_files() {
    let home = unique_home();
    fs::create_dir_all(&home).expect("temp home should be created");

    assert_success(&run_wok(&home, &["init"]));
    let cfg_dir = config_dir(&home);
    fs::write(cfg_dir.join("session.json"), "{}").expect("session file should be seeded");
    fs::create_dir_all(cfg_dir.join("sessions")).expect("sessions dir should be seeded");
    fs::write(cfg_dir.join("sessions").join("demo.json"), "{}")
        .expect("session snapshot should be seeded");

    assert_success(&run_wok(&home, &["reset", "--scope", "state", "--yes"]));

    assert!(cfg_dir.join("config.toml").exists());
    assert!(cfg_dir.join("init.lua").exists());
    assert!(!cfg_dir.join("session.json").exists());
    assert!(!cfg_dir.join("sessions").exists());
}

#[test]
fn shell_install_and_rollback_restore_previous_shell_file() {
    let home = unique_home();
    fs::create_dir_all(&home).expect("temp home should be created");
    assert_success(&run_wok(&home, &["init"]));

    let zshrc = home.join(".zshrc");
    fs::write(&zshrc, "export FOO=BAR\n").expect("seed zshrc should be written");

    assert_success(&run_wok(&home, &["shell", "install", "--shell", "zsh"]));
    let updated = fs::read_to_string(&zshrc).expect("updated zshrc should be readable");
    assert!(
        updated.contains("# >>> wok shell integration >>>"),
        "install should insert marker block"
    );
    assert!(
        zshrc.with_extension("zshrc.wok.bak").exists()
            || PathBuf::from(format!("{}.wok.bak", zshrc.display())).exists()
    );

    assert_success(&run_wok(&home, &["shell", "rollback", "--yes"]));
    let rolled_back = fs::read_to_string(&zshrc).expect("rolled back zshrc should be readable");
    assert_eq!(rolled_back, "export FOO=BAR\n");
}

#[test]
fn shell_rollback_can_target_individual_shell_when_multiple_installs_exist() {
    let home = unique_home();
    fs::create_dir_all(&home).expect("temp home should be created");
    assert_success(&run_wok(&home, &["init"]));

    let bashrc = home.join(".bashrc");
    let zshrc = home.join(".zshrc");
    fs::write(&bashrc, "export BASH_ONLY=1\n").expect("seed bashrc should be written");
    fs::write(&zshrc, "export ZSH_ONLY=1\n").expect("seed zshrc should be written");

    assert_success(&run_wok(&home, &["shell", "install", "--shell", "bash"]));
    assert_success(&run_wok(&home, &["shell", "install", "--shell", "zsh"]));

    let rollback_without_shell = run_wok(&home, &["shell", "rollback", "--yes"]);
    assert_failure(&rollback_without_shell);

    assert_success(&run_wok(
        &home,
        &["shell", "rollback", "--shell", "zsh", "--yes"],
    ));
    let zsh_content = fs::read_to_string(&zshrc).expect("zshrc should be readable");
    assert_eq!(zsh_content, "export ZSH_ONLY=1\n");

    let bash_content_after_zsh_rollback =
        fs::read_to_string(&bashrc).expect("bashrc should be readable");
    assert!(
        bash_content_after_zsh_rollback.contains("# >>> wok shell integration >>>"),
        "bash install should still be present after zsh rollback"
    );

    assert_success(&run_wok(
        &home,
        &["shell", "rollback", "--shell", "bash", "--yes"],
    ));
    let bash_content = fs::read_to_string(&bashrc).expect("bashrc should be readable");
    assert_eq!(bash_content, "export BASH_ONLY=1\n");
}
