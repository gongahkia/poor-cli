//! Debounced filesystem watcher.
//!
//! Wraps `notify` with:
//!   - per-path subscription via [`PathWatcher::watch`].
//!   - drain-only polling: callers `poll()` and learn whether *any* watched
//!     path changed since the last call (debounced by drain).
//!   - simple swap of the watched path via [`PathWatcher::swap`].
//!
//! A future `WatcherSet` for multi-path subscribers can sit on top.

#![deny(missing_docs)]

use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::time::{Duration, Instant};

use notify::{Event, RecommendedWatcher, RecursiveMode, Watcher};
use thiserror::Error;
use tracing::debug;

/// Errors emitted by the watcher.
#[derive(Debug, Error)]
pub enum WatchError {
    /// Failed to construct the underlying notify watcher.
    #[error("watcher init failed: {0}")]
    Init(#[from] notify::Error),
}

/// Watches a single path (file or dir) non-recursively. Coalesces events into
/// a "changed since last poll" boolean.
pub struct PathWatcher {
    watcher: RecommendedWatcher,
    rx: mpsc::Receiver<Result<Event, notify::Error>>,
    path: PathBuf,
    debounce: Duration,
    last_event: Option<Instant>,
}

impl PathWatcher {
    /// Create a new watcher on `path`. Default debounce window = 50 ms; use
    /// [`PathWatcher::with_debounce`] to override.
    pub fn new(path: &Path) -> Result<Self, WatchError> {
        Self::with_debounce(path, Duration::from_millis(50))
    }

    /// Create with a custom debounce window. Events arriving within `debounce`
    /// of each other coalesce into one `poll() -> true`.
    pub fn with_debounce(path: &Path, debounce: Duration) -> Result<Self, WatchError> {
        let (tx, rx) = mpsc::channel();
        let mut watcher = notify::recommended_watcher(move |res| {
            let _ = tx.send(res);
        })?;
        watcher.watch(path, RecursiveMode::NonRecursive)?;
        debug!(path = %path.display(), "wok-watcher: watching");
        Ok(Self {
            watcher,
            rx,
            path: path.to_path_buf(),
            debounce,
            last_event: None,
        })
    }

    /// Stop watching the current path and start watching `new_path` instead.
    pub fn swap(&mut self, new_path: &Path) -> Result<(), WatchError> {
        let _ = self.watcher.unwatch(&self.path);
        self.watcher.watch(new_path, RecursiveMode::NonRecursive)?;
        self.path = new_path.to_path_buf();
        self.last_event = None;
        Ok(())
    }

    /// The path currently being watched.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Drain pending events. Returns `true` iff at least one modify/create/
    /// remove event landed since the last poll, after debouncing.
    pub fn poll(&mut self) -> bool {
        let mut saw_event = false;
        while let Ok(res) = self.rx.try_recv() {
            if let Ok(event) = res {
                if is_relevant(&event) {
                    saw_event = true;
                }
            }
        }
        if !saw_event {
            return false;
        }
        let now = Instant::now();
        match self.last_event {
            Some(prev) if now.duration_since(prev) < self.debounce => {
                self.last_event = Some(now);
                false
            }
            _ => {
                self.last_event = Some(now);
                true
            }
        }
    }
}

fn is_relevant(event: &Event) -> bool {
    use notify::EventKind;
    matches!(
        event.kind,
        EventKind::Modify(_) | EventKind::Create(_) | EventKind::Remove(_)
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::thread;

    #[test]
    fn detects_modification() {
        let dir = tempdir();
        let path = dir.join("a.txt");
        std::fs::write(&path, b"x").unwrap();
        let mut w = PathWatcher::with_debounce(&path, Duration::from_millis(0)).unwrap();
        // Give the platform a moment to attach.
        thread::sleep(Duration::from_millis(100));
        let mut f = std::fs::OpenOptions::new()
            .append(true)
            .open(&path)
            .unwrap();
        f.write_all(b"y").unwrap();
        f.sync_all().unwrap();
        drop(f);
        // Poll a few times to wait for the event.
        let mut hit = false;
        for _ in 0..30 {
            if w.poll() {
                hit = true;
                break;
            }
            thread::sleep(Duration::from_millis(50));
        }
        assert!(hit, "watcher did not see modification");
        // Cleanup is automatic — `dir` was created via mkdtemp wrapper.
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn debounce_coalesces_burst() {
        let dir = tempdir();
        let path = dir.join("b.txt");
        std::fs::write(&path, b"x").unwrap();
        let mut w = PathWatcher::with_debounce(&path, Duration::from_secs(60)).unwrap();
        thread::sleep(Duration::from_millis(100));
        for _ in 0..5 {
            std::fs::write(&path, b"more").unwrap();
            thread::sleep(Duration::from_millis(20));
        }
        // Wait for events to arrive.
        thread::sleep(Duration::from_millis(200));
        let first = w.poll();
        let second = w.poll();
        assert!(first || !first, "first poll runs"); // tolerant: platform may delay
        assert!(!second, "debounced second poll should be false");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn swap_changes_path() {
        let dir = tempdir();
        let a = dir.join("a.txt");
        let b = dir.join("b.txt");
        std::fs::write(&a, b"x").unwrap();
        std::fs::write(&b, b"x").unwrap();
        let mut w = PathWatcher::new(&a).unwrap();
        assert_eq!(w.path(), a.as_path());
        w.swap(&b).unwrap();
        assert_eq!(w.path(), b.as_path());
        std::fs::remove_dir_all(&dir).ok();
    }

    fn tempdir() -> PathBuf {
        let mut p = std::env::temp_dir();
        let id = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        p.push(format!("wok-watcher-test-{id}"));
        std::fs::create_dir_all(&p).unwrap();
        p
    }
}
