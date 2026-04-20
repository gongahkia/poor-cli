#![cfg(unix)]

use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use wok_terminal::shell::ShellType;

struct SessionCleanup {
    name: String,
}

impl SessionCleanup {
    fn new(name: String) -> Self {
        Self { name }
    }
}

impl Drop for SessionCleanup {
    fn drop(&mut self) {
        let _ = wok_app::daemon::kill_session(&self.name);
    }
}

fn unique_session_name() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("current time should be after epoch")
        .as_nanos();
    format!("wok-it-{}-{nanos}", std::process::id())
}

fn wait_until(timeout: Duration, step: Duration, mut check: impl FnMut() -> bool) -> bool {
    let start = std::time::Instant::now();
    while start.elapsed() < timeout {
        if check() {
            return true;
        }
        thread::sleep(step);
    }
    check()
}

#[test]
fn daemon_lifecycle_supports_attach_input_snapshot_and_kill() {
    let session = unique_session_name();
    let _cleanup = SessionCleanup::new(session.clone());
    let daemon_session = session.clone();

    let daemon_thread = thread::spawn(move || {
        wok_app::daemon::run_daemon_with_shell(&daemon_session, &ShellType::Bash)
            .map_err(|error| error.to_string())
    });

    let attached = wait_until(Duration::from_secs(3), Duration::from_millis(50), || {
        wok_app::daemon::attach_session(&session).is_ok()
    });
    assert!(attached, "daemon session should accept attach requests");

    let listed = wait_until(Duration::from_secs(2), Duration::from_millis(50), || {
        wok_app::daemon::list_sessions()
            .iter()
            .any(|item| item.name == session)
    });
    assert!(listed, "daemon session should appear in session list");

    let command = "echo WOK_DAEMON_LIFECYCLE\necho \"$WOK_SESSION\"\nif [ -n \"$WOK_SESSION_SOCKET\" ]; then echo WOK_SESSION_SOCKET_SET; fi\n".to_string();
    wok_app::daemon::send_input(&session, 0, command.as_bytes())
        .expect("daemon should accept pane input");
    wok_app::daemon::resize_pane(&session, 0, 100, 30).expect("daemon should resize pane");
    assert!(
        wok_app::daemon::send_input(&session, 9, b"echo SHOULD_NOT_APPEAR\n").is_err(),
        "daemon should reject unknown pane ids for input"
    );
    assert!(
        wok_app::daemon::resize_pane(&session, 9, 80, 24).is_err(),
        "daemon should reject unknown pane ids for resize"
    );

    let snapshot_contains_output =
        wait_until(Duration::from_secs(5), Duration::from_millis(75), || {
            wok_app::daemon::snapshot_session(&session)
                .ok()
                .and_then(|snapshot| {
                    snapshot
                        .get("rows")
                        .and_then(serde_json::Value::as_array)
                        .cloned()
                })
                .is_some_and(|rows| {
                    let texts = rows
                        .iter()
                        .filter_map(|row| row.get("text").and_then(serde_json::Value::as_str))
                        .collect::<Vec<_>>();
                    texts
                        .iter()
                        .any(|text| text.contains("WOK_DAEMON_LIFECYCLE"))
                        && texts.iter().any(|text| text.contains(&session))
                        && texts
                            .iter()
                            .any(|text| text.contains("WOK_SESSION_SOCKET_SET"))
                })
        });
    assert!(
        snapshot_contains_output,
        "daemon snapshot should include command output text"
    );

    let pane_snapshot_ok = wait_until(Duration::from_secs(3), Duration::from_millis(75), || {
        wok_app::daemon::snapshot_session(&session)
            .ok()
            .and_then(|snapshot| {
                snapshot
                    .get("panes")
                    .and_then(serde_json::Value::as_array)
                    .cloned()
            })
            .is_some_and(|panes| {
                panes.iter().any(|pane| {
                    pane.get("pane_id")
                        .and_then(serde_json::Value::as_u64)
                        .is_some_and(|pane_id| pane_id == 0)
                        && pane
                            .get("rows")
                            .and_then(serde_json::Value::as_array)
                            .is_some()
                })
            })
    });
    assert!(
        pane_snapshot_ok,
        "daemon snapshot should include pane-scoped rows payload"
    );

    wok_app::daemon::detach_session(&session).expect("daemon should accept detach");
    wok_app::daemon::kill_session(&session).expect("daemon should accept kill");

    let run_result = daemon_thread
        .join()
        .expect("daemon thread should join without panic");
    run_result.expect("daemon loop should exit cleanly");
}
