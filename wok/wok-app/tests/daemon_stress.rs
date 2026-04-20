//! Stress-oriented local integration tests for daemon runtime.
#![cfg(unix)]

use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::Duration;
use std::time::{SystemTime, UNIX_EPOCH};

static SESSION_COUNTER: AtomicU64 = AtomicU64::new(0);

fn unique_session(prefix: &str) -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("current time should be after epoch")
        .as_millis() as u64;
    let seed = millis & 0xffff;
    let counter = SESSION_COUNTER.fetch_add(1, Ordering::Relaxed);
    format!(
        "{prefix}_stress_{}_{seed:x}_{counter:x}",
        std::process::id()
    )
}

fn wait_for_session(name: &str, timeout: Duration) -> bool {
    let start = std::time::Instant::now();
    while start.elapsed() < timeout {
        if wok_app::daemon::query_session(name).is_some() {
            return true;
        }
        thread::sleep(Duration::from_millis(50));
    }
    false
}

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

#[test]
fn repeated_attach_detach_cycles() {
    let name = unique_session("attach_detach");
    let _cleanup = SessionCleanup::new(name.clone());
    let handle = thread::spawn({
        let name = name.clone();
        move || wok_app::daemon::run_daemon(&name).unwrap()
    });
    assert!(wait_for_session(&name, Duration::from_secs(5)));

    for _ in 0..10 {
        let summary = wok_app::daemon::attach_session(&name).unwrap();
        assert!(summary.running);
        wok_app::daemon::detach_session(&name).unwrap();
    }

    wok_app::daemon::kill_session(&name).unwrap();
    handle.join().unwrap();
}

#[test]
fn multiple_concurrent_snapshot_requests() {
    let name = unique_session("concurrent_snap");
    let _cleanup = SessionCleanup::new(name.clone());
    let handle = thread::spawn({
        let name = name.clone();
        move || wok_app::daemon::run_daemon(&name).unwrap()
    });
    assert!(wait_for_session(&name, Duration::from_secs(5)));
    wok_app::daemon::attach_session(&name).unwrap();

    let mut handles = Vec::new();
    for _ in 0..5 {
        let name = name.clone();
        handles.push(thread::spawn(move || {
            wok_app::daemon::snapshot_session(&name).unwrap()
        }));
    }
    for h in handles {
        let snap = h.join().unwrap();
        assert!(snap.get("session").is_some() || snap.get("panes").is_some()); // daemon snapshot has structure
    }

    wok_app::daemon::kill_session(&name).unwrap();
    handle.join().unwrap();
}

#[test]
fn invalid_pane_operations_return_errors() {
    let name = unique_session("invalid_ops");
    let _cleanup = SessionCleanup::new(name.clone());
    let handle = thread::spawn({
        let name = name.clone();
        move || wok_app::daemon::run_daemon(&name).unwrap()
    });
    assert!(wait_for_session(&name, Duration::from_secs(5)));

    let result = wok_app::daemon::send_input(&name, 999, b"hello");
    assert!(result.is_err());

    let result = wok_app::daemon::resize_pane(&name, 999, 80, 24);
    assert!(result.is_err());

    wok_app::daemon::kill_session(&name).unwrap();
    handle.join().unwrap();
}

#[test]
fn create_and_close_pane_churn() {
    let name = unique_session("pane_churn");
    let _cleanup = SessionCleanup::new(name.clone());
    let handle = thread::spawn({
        let name = name.clone();
        move || wok_app::daemon::run_daemon(&name).unwrap()
    });
    assert!(wait_for_session(&name, Duration::from_secs(5)));

    let mut pane_ids = Vec::new();
    for _ in 0..3 {
        let id = wok_app::daemon::create_pane(&name, "vertical").unwrap();
        pane_ids.push(id);
    }

    let panes = wok_app::daemon::list_panes(&name).unwrap();
    assert_eq!(panes.len(), 4); // 1 original + 3 created

    for id in pane_ids {
        wok_app::daemon::close_pane(&name, id).unwrap();
    }

    let panes = wok_app::daemon::list_panes(&name).unwrap();
    assert_eq!(panes.len(), 1);

    let result = wok_app::daemon::close_pane(&name, 0);
    assert!(result.is_err()); // cannot close last pane

    wok_app::daemon::kill_session(&name).unwrap();
    handle.join().unwrap();
}
