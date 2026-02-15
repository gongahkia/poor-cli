use notify::{Event, EventKind, RecursiveMode, Watcher};
use std::path::{Path, PathBuf};
use std::sync::{mpsc, Arc};

/// File watcher for live reload (Task 18)
/// The on_change callback receives Ok(()) on success or Err(message) on file read failure.
pub fn watch_file<F>(path: &Path, on_change: F) -> Result<notify::RecommendedWatcher, notify::Error>
where
    F: Fn(Result<(), String>) + Send + 'static,
{
    let (tx, rx) = mpsc::channel();
    let watched_path = path.to_path_buf();

    let mut watcher =
        notify::recommended_watcher(move |res: Result<Event, notify::Error>| match res {
            Ok(event) => match event.kind {
                EventKind::Modify(_) | EventKind::Create(_) => {
                    let _ = tx.send(Ok(()));
                }
                _ => {}
            },
            Err(e) => {
                let _ = tx.send(Err(format!("watcher error: {}", e)));
            }
        })?;

    watcher.watch(path, RecursiveMode::NonRecursive)?;

    // Debounce thread with error handling for file read failures
    std::thread::spawn(move || {
        let mut last = std::time::Instant::now();
        while let Ok(result) = rx.recv() {
            let now = std::time::Instant::now();
            if now.duration_since(last).as_millis() > 300 {
                match result {
                    Ok(()) => {
                        // Verify file is still readable before calling back
                        match std::fs::read_to_string(&watched_path) {
                            Ok(_) => on_change(Ok(())),
                            Err(e) => on_change(Err(format!("file read error: {}", e))),
                        }
                    }
                    Err(e) => on_change(Err(e)),
                }
                last = now;
            }
        }
    });

    Ok(watcher)
}
