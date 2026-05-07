#![cfg(unix)]

use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixListener;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};

static TMP_COUNTER: AtomicU64 = AtomicU64::new(0);

fn unique_temp_dir(prefix: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time should be after epoch")
        .as_nanos();
    let counter = TMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!(
        "wok-rpc-it-{prefix}-{}-{nanos}-{counter}",
        std::process::id()
    ))
}

fn unique_socket_path() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time should be after epoch")
        .as_nanos();
    let counter = TMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!(
        "wok-rpc-{}-{nanos}-{counter}.sock",
        std::process::id()
    ))
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
        .env_remove("WOK_RPC_TOKEN")
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

fn run_wok_with_env(home: &Path, args: &[&str], env: &[(&str, &str)]) -> Output {
    let bin = std::env::var("CARGO_BIN_EXE_wok")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("target")
                .join("debug")
                .join("wok")
        });
    let mut command = Command::new(bin);
    command.args(args);
    command.env("HOME", home);
    command.env_remove("WOK_RPC_TOKEN");
    command.env(
        "RUSTUP_HOME",
        std::env::var("RUSTUP_HOME").unwrap_or_else(|_| {
            format!(
                "{}/.rustup",
                std::env::var("HOME").expect("parent HOME should be available")
            )
        }),
    );
    command.env(
        "CARGO_HOME",
        std::env::var("CARGO_HOME").unwrap_or_else(|_| {
            format!(
                "{}/.cargo",
                std::env::var("HOME").expect("parent HOME should be available")
            )
        }),
    );
    for (key, value) in env {
        command.env(key, value);
    }
    command.output().expect("wok command should execute")
}

fn assert_success(output: &Output) {
    assert!(
        output.status.success(),
        "command failed\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

fn spawn_mock_rpc_server(
    socket_path: PathBuf,
    expected_request: Value,
    response: Option<Value>,
) -> thread::JoinHandle<()> {
    let parent = socket_path
        .parent()
        .expect("socket path should have a parent directory")
        .to_path_buf();
    fs::create_dir_all(&parent).expect("socket parent should exist");
    if socket_path.exists() {
        fs::remove_file(&socket_path).expect("stale socket should be removed");
    }
    let listener = UnixListener::bind(&socket_path).expect("mock socket should bind");

    thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("mock server should accept client");
        let mut request_line = String::new();
        {
            let mut reader = BufReader::new(&mut stream);
            reader
                .read_line(&mut request_line)
                .expect("mock server should read request line");
        }
        let request: Value =
            serde_json::from_str(request_line.trim()).expect("request json should parse");
        assert_eq!(request, expected_request, "unexpected RPC request payload");

        if let Some(response_json) = response {
            let mut payload =
                serde_json::to_vec(&response_json).expect("response json should encode");
            payload.push(b'\n');
            stream
                .write_all(&payload)
                .expect("mock server should write response");
        }
    })
}

#[test]
fn rpc_cli_sends_setup_lifecycle_methods_with_expected_payloads() {
    let home = unique_temp_dir("setup");
    fs::create_dir_all(&home).expect("temp home should be created");

    let cases = vec![
        ("wok.setup.init", r#"{"overwrite":true}"#),
        ("wok.setup.doctor", r#"{"json":true}"#),
        ("wok.setup.reset", r#"{"scope":"managed","yes":true}"#),
        (
            "wok.setup.shell_install",
            r#"{"shell":"zsh","overwrite":false}"#,
        ),
        ("wok.setup.shell_rollback", r#"{"shell":"zsh","yes":true}"#),
    ];

    for (method, params) in cases {
        let socket_path = unique_socket_path();
        let expected_request = json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": serde_json::from_str::<Value>(params).expect("params should parse"),
            "id": 1
        });
        let server = spawn_mock_rpc_server(
            socket_path.clone(),
            expected_request,
            Some(json!({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"ok": true}
            })),
        );

        let output = run_wok(
            &home,
            &[
                "rpc",
                method,
                "--params",
                params,
                "--socket",
                &socket_path.display().to_string(),
            ],
        );
        assert_success(&output);

        let response: Value =
            serde_json::from_slice(&output.stdout).expect("rpc response should parse as json");
        assert_eq!(response["result"]["ok"], Value::Bool(true));
        server
            .join()
            .expect("mock server thread should finish cleanly");
    }
}

#[test]
fn rpc_cli_sends_failure_trends_request_and_prints_result() {
    let home = unique_temp_dir("trends");
    fs::create_dir_all(&home).expect("temp home should be created");

    let socket_path = unique_socket_path();
    let expected_request = json!({
        "jsonrpc": "2.0",
        "method": "wok.get_failure_trends",
        "params": [0, 120000, 5],
        "id": 1
    });
    let server = spawn_mock_rpc_server(
        socket_path.clone(),
        expected_request,
        Some(json!({
            "jsonrpc": "2.0",
            "id": 1,
            "result": [{
                "command": "cargo test",
                "cwd": "/repo",
                "branch": "main",
                "bucket_start_ms": 123000,
                "count": 2,
                "last_exit_code": 101,
                "last_completed_at_ms": 123999
            }]
        })),
    );

    let output = run_wok(
        &home,
        &[
            "rpc",
            "wok.get_failure_trends",
            "--params",
            "[0,120000,5]",
            "--socket",
            &socket_path.display().to_string(),
        ],
    );
    assert_success(&output);

    let response: Value =
        serde_json::from_slice(&output.stdout).expect("rpc response should parse as json");
    assert_eq!(
        response["result"][0]["command"],
        Value::String("cargo test".to_string())
    );
    assert_eq!(response["result"][0]["count"], Value::from(2_u64));
    server
        .join()
        .expect("mock server thread should finish cleanly");
}

#[test]
fn git_status_cli_calls_rpc_and_prints_result_payload() {
    let home = unique_temp_dir("git-status");
    fs::create_dir_all(&home).expect("temp home should be created");

    let socket_path = unique_socket_path();
    let expected_request = json!({
        "jsonrpc": "2.0",
        "method": "wok.get_git_status",
        "params": {"pane_id": 3},
        "id": 1
    });
    let server = spawn_mock_rpc_server(
        socket_path.clone(),
        expected_request,
        Some(json!({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "pane_id": 3,
                "is_git_repo": true,
                "repo_root": "/repo",
                "branch": "main",
                "clean": false,
                "files": [{"path": "src/lib.rs", "status_text": "M"}]
            }
        })),
    );

    let output = run_wok(
        &home,
        &[
            "git-status",
            "--pane-id",
            "3",
            "--socket",
            &socket_path.display().to_string(),
        ],
    );
    assert_success(&output);

    let response: Value =
        serde_json::from_slice(&output.stdout).expect("git-status output should parse as json");
    assert_eq!(response["pane_id"], Value::from(3_u64));
    assert_eq!(
        response["files"][0]["path"],
        Value::String("src/lib.rs".to_string())
    );
    assert!(
        response.get("jsonrpc").is_none(),
        "should print result only"
    );
    server
        .join()
        .expect("mock server thread should finish cleanly");
}

#[test]
fn worktree_cli_calls_rpc_and_prints_result_payload() {
    let home = unique_temp_dir("worktree-list");
    fs::create_dir_all(&home).expect("temp home should be created");

    let socket_path = unique_socket_path();
    let expected_request = json!({
        "jsonrpc": "2.0",
        "method": "wok.worktree.list",
        "params": {},
        "id": 1
    });
    let server = spawn_mock_rpc_server(
        socket_path.clone(),
        expected_request,
        Some(json!({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "repo_key": "abc",
                "active_id": "main",
                "worktrees": [{
                    "id": "main",
                    "name": "main",
                    "path": "/repo",
                    "branch": "main",
                    "source": "primary",
                    "owns_branch": false,
                    "is_primary": true,
                    "created_at": 1
                }]
            }
        })),
    );

    let output = run_wok(
        &home,
        &[
            "worktree",
            "list",
            "--socket",
            &socket_path.display().to_string(),
        ],
    );
    assert_success(&output);

    let response: Value =
        serde_json::from_slice(&output.stdout).expect("worktree output should parse as json");
    assert_eq!(response["repo_key"], Value::String("abc".to_string()));
    assert_eq!(
        response["worktrees"][0]["id"],
        Value::String("main".to_string())
    );
    server
        .join()
        .expect("mock server thread should finish cleanly");
}

#[test]
fn rpc_cli_supports_explicit_token_flag() {
    let home = unique_temp_dir("token-flag");
    fs::create_dir_all(&home).expect("temp home should be created");

    let socket_path = unique_socket_path();
    let expected_request = json!({
        "jsonrpc": "2.0",
        "method": "wok.get_panes",
        "params": null,
        "auth_token": "token-from-flag",
        "id": 1
    });
    let server = spawn_mock_rpc_server(
        socket_path.clone(),
        expected_request,
        Some(json!({"jsonrpc":"2.0","id":1,"result":[] })),
    );

    let output = run_wok(
        &home,
        &[
            "rpc",
            "wok.get_panes",
            "--socket",
            &socket_path.display().to_string(),
            "--token",
            "token-from-flag",
        ],
    );
    assert_success(&output);
    server
        .join()
        .expect("mock server thread should finish cleanly");
}

#[test]
fn rpc_cli_reads_token_from_environment() {
    let home = unique_temp_dir("token-env");
    fs::create_dir_all(&home).expect("temp home should be created");

    let socket_path = unique_socket_path();
    let expected_request = json!({
        "jsonrpc": "2.0",
        "method": "wok.get_panes",
        "params": null,
        "auth_token": "token-from-env",
        "id": 1
    });
    let server = spawn_mock_rpc_server(
        socket_path.clone(),
        expected_request,
        Some(json!({"jsonrpc":"2.0","id":1,"result":[] })),
    );

    let output = run_wok_with_env(
        &home,
        &[
            "rpc",
            "wok.get_panes",
            "--socket",
            &socket_path.display().to_string(),
        ],
        &[("WOK_RPC_TOKEN", "token-from-env")],
    );
    assert_success(&output);
    server
        .join()
        .expect("mock server thread should finish cleanly");
}
