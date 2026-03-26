// app state: manages the poor-cli-server subprocess and JSON-RPC communication.

use std::sync::Mutex;
use tokio::process::Child;

pub struct BackendProcess {
    pub child: Child,
    pub stdin: tokio::process::ChildStdin,
    pub stdout: tokio::io::BufReader<tokio::process::ChildStdout>,
}

#[derive(Default)]
pub struct AppState {
    pub backend: Mutex<Option<BackendProcess>>,
    pub initialized: Mutex<bool>,
    pub request_id: Mutex<u64>,
}

impl AppState {
    pub fn next_request_id(&self) -> u64 {
        let mut id = self.request_id.lock().unwrap();
        *id += 1;
        *id
    }
}
