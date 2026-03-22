//! Asynchronous PTY I/O: spawns a reader thread for non-blocking PTY communication.

use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};

use crossbeam_channel::{bounded, Receiver, Sender};
use tracing::{debug, warn};

use crate::pty::{PtyError, SpawnedPty};
use crate::shell_integration::ShellBootstrap;

/// Events from the PTY reader thread.
#[derive(Debug)]
pub enum PtyEvent {
    /// Raw bytes read from PTY output.
    Data(Vec<u8>),
    /// The shell process exited with the given code.
    Exited(i32),
    /// An error occurred reading from the PTY.
    Error(String),
}

/// Handle for asynchronous PTY I/O.
///
/// Owns a reader thread that sends `PtyEvent`s through a bounded channel,
/// and provides synchronized write access to the PTY.
pub struct PtyIoHandle {
    master: Box<dyn portable_pty::MasterPty + Send>,
    writer: Arc<Mutex<Box<dyn Write + Send>>>,
    killer: Arc<Mutex<Box<dyn portable_pty::ChildKiller + Send + Sync>>>,
    rx: Receiver<PtyEvent>,
    _shell_bootstrap: Option<ShellBootstrap>,
    _reader_thread: JoinHandle<()>,
    _wait_thread: JoinHandle<()>,
}

impl PtyIoHandle {
    /// Create a new async I/O handle from a spawned PTY bundle.
    ///
    /// Spawns a dedicated reader thread that reads up to 64KB at a time
    /// and a dedicated waiter thread that reports the child process exit code.
    pub fn new(spawned: SpawnedPty) -> Self {
        let (tx, rx): (Sender<PtyEvent>, Receiver<PtyEvent>) = bounded(256);
        let writer = Arc::new(Mutex::new(spawned.writer));
        let killer = Arc::new(Mutex::new(spawned.child.clone_killer()));
        let reader_tx = tx.clone();
        let mut reader = spawned.reader;

        let reader_thread = thread::Builder::new()
            .name("pty-reader".to_string())
            .spawn(move || {
                let mut buf = vec![0u8; 65_536]; // 64KB buffer
                loop {
                    match reader.read(&mut buf) {
                        Ok(0) => {
                            debug!("PTY reader: EOF");
                            break;
                        }
                        Ok(n) => {
                            if reader_tx.send(PtyEvent::Data(buf[..n].to_vec())).is_err() {
                                debug!("PTY reader: channel disconnected");
                                break;
                            }
                        }
                        Err(e) => {
                            warn!("PTY reader error: {e}");
                            let _ = reader_tx.send(PtyEvent::Error(e.to_string()));
                            break;
                        }
                    }
                }
            })
            .expect("failed to spawn PTY reader thread");

        let mut child = spawned.child;
        let wait_thread = thread::Builder::new()
            .name("pty-wait".to_string())
            .spawn(move || match child.wait() {
                Ok(status) => {
                    let code = i32::try_from(status.exit_code()).ok().unwrap_or(i32::MAX);
                    let _ = tx.send(PtyEvent::Exited(code));
                }
                Err(e) => {
                    let _ = tx.send(PtyEvent::Error(e.to_string()));
                }
            })
            .expect("failed to spawn PTY wait thread");

        Self {
            master: spawned.master,
            writer,
            killer,
            rx,
            _shell_bootstrap: spawned.shell_bootstrap,
            _reader_thread: reader_thread,
            _wait_thread: wait_thread,
        }
    }

    /// Non-blocking receive of the next PTY event.
    pub fn try_recv(&self) -> Option<PtyEvent> {
        self.rx.try_recv().ok()
    }

    /// Write data to the PTY.
    ///
    /// # Errors
    ///
    /// Returns [`PtyError::Io`] if the write fails.
    pub fn write(&self, data: &[u8]) -> Result<(), PtyError> {
        let mut writer = self
            .writer
            .lock()
            .map_err(|_| PtyError::ChannelDisconnected)?;
        writer.write_all(data)?;
        writer.flush()?;
        Ok(())
    }

    /// Resize the underlying PTY.
    ///
    /// # Errors
    ///
    /// Returns [`PtyError::ResizeFailed`] if the kernel PTY resize fails.
    pub fn resize(&mut self, cols: u16, rows: u16) -> Result<(), PtyError> {
        self.master
            .resize(portable_pty::PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| PtyError::ResizeFailed(e.to_string()))
    }
}

impl Drop for PtyIoHandle {
    fn drop(&mut self) {
        if let Ok(mut killer) = self.killer.lock() {
            let _ = killer.kill();
        }
    }
}
