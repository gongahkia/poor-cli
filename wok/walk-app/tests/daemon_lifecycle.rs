#![cfg(unix)]

use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use walk_terminal::shell::ShellType;

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
        let _ = walk_app::daemon::kill_session(&self.name);
    }
}

fn unique_session_name() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("current time should be after epoch")
        .as_nanos();
    format!("walk-it-{}-{nanos}", std::process::id())
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
        walk_app::daemon::run_daemon_with_shell(&daemon_session, &ShellType::Bash)
            .map_err(|error| error.to_string())
    });

    let attached = wait_until(Duration::from_secs(3), Duration::from_millis(50), || {
        walk_app::daemon::attach_session(&session).is_ok()
    });
    assert!(attached, "daemon session should accept attach requests");

    let listed = wait_until(Duration::from_secs(2), Duration::from_millis(50), || {
        walk_app::daemon::list_sessions()
            .iter()
            .any(|item| item.name == session)
    });
    assert!(listed, "daemon session should appear in session list");

    walk_app::daemon::send_input(&session, 0, b"echo WALK_DAEMON_LIFECYCLE\n")
        .expect("daemon should accept pane input");
    walk_app::daemon::resize_pane(&session, 0, 100, 30).expect("daemon should resize pane");

    let snapshot_contains_output =
        wait_until(Duration::from_secs(5), Duration::from_millis(75), || {
            walk_app::daemon::snapshot_session(&session)
                .ok()
                .and_then(|snapshot| {
                    snapshot
                        .get("rows")
                        .and_then(serde_json::Value::as_array)
                        .cloned()
                })
                .is_some_and(|rows| {
                    rows.iter().any(|row| {
                        row.get("text")
                            .and_then(serde_json::Value::as_str)
                            .is_some_and(|text| text.contains("WALK_DAEMON_LIFECYCLE"))
                    })
                })
        });
    assert!(
        snapshot_contains_output,
        "daemon snapshot should include command output text"
    );

    walk_app::daemon::detach_session(&session).expect("daemon should accept detach");
    walk_app::daemon::kill_session(&session).expect("daemon should accept kill");

    let run_result = daemon_thread
        .join()
        .expect("daemon thread should join without panic");
    run_result.expect("daemon loop should exit cleanly");
}
