use notify::{Watcher, RecursiveMode, Event, EventKind};
use std::path::Path;
use std::sync::{Arc, mpsc};

/// File watcher for live reload (Task 18)
pub fn watch_file<F>(path: &Path, on_change: F) -> Result<notify::RecommendedWatcher, notify::Error>
where
    F: Fn() + Send + 'static,
{
    let (tx, rx) = mpsc::channel();

    let mut watcher = notify::recommended_watcher(move |res: Result<Event, notify::Error>| {
        if let Ok(event) = res {
            match event.kind {
                EventKind::Modify(_) | EventKind::Create(_) => {
                    let _ = tx.send(());
                }
                _ => {}
            }
        }
    })?;

    watcher.watch(path, RecursiveMode::NonRecursive)?;

    // Debounce thread
    std::thread::spawn(move || {
        let mut last = std::time::Instant::now();
        while rx.recv().is_ok() {
            let now = std::time::Instant::now();
            if now.duration_since(last).as_millis() > 300 {
                on_change();
                last = now;
            }
        }
    });

    Ok(watcher)
}
