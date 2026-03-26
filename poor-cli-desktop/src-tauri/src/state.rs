// app state: manages the poor-cli-server subprocess and JSON-RPC communication.

use std::sync::atomic::{AtomicU64, Ordering};
use tokio::sync::Mutex;
use tokio::process::Child;

pub struct BackendProcess {
    pub _child: Child,
    pub stdin: tokio::process::ChildStdin,
    pub stdout: tokio::io::BufReader<tokio::process::ChildStdout>,
}

pub struct AppState {
    pub backend: Mutex<Option<BackendProcess>>,
    pub initialized: Mutex<bool>,
    request_id: AtomicU64,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            backend: Mutex::new(None),
            initialized: Mutex::new(false),
            request_id: AtomicU64::new(0),
        }
    }
}

impl AppState {
    pub fn next_request_id(&self) -> u64 {
        self.request_id.fetch_add(1, Ordering::Relaxed) + 1
    }
}
