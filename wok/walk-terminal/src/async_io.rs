//! Asynchronous PTY I/O: spawns a reader thread for non-blocking PTY communication.

use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};

use crossbeam_channel::{bounded, Receiver, Sender};
use tracing::{debug, warn};

use crate::pty::PtyError;

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
    writer: Arc<Mutex<Box<dyn Write + Send>>>,
    rx: Receiver<PtyEvent>,
    _reader_thread: JoinHandle<()>,
}

impl PtyIoHandle {
    /// Create a new async I/O handle from a PTY reader and writer.
    ///
    /// Spawns a dedicated reader thread that reads up to 64KB at a time
    /// and sends data through a bounded(256) channel.
    pub fn new(
        mut reader: Box<dyn Read + Send>,
        writer: Box<dyn Write + Send>,
    ) -> Self {
        let (tx, rx): (Sender<PtyEvent>, Receiver<PtyEvent>) = bounded(256);
        let writer = Arc::new(Mutex::new(writer));

        let reader_thread = thread::Builder::new()
            .name("pty-reader".to_string())
            .spawn(move || {
                let mut buf = vec![0u8; 65_536]; // 64KB buffer
                loop {
                    match reader.read(&mut buf) {
                        Ok(0) => {
                            debug!("PTY reader: EOF");
                            let _ = tx.send(PtyEvent::Exited(0));
                            break;
                        }
                        Ok(n) => {
                            if tx.send(PtyEvent::Data(buf[..n].to_vec())).is_err() {
                                debug!("PTY reader: channel disconnected");
                                break;
                            }
                        }
                        Err(e) => {
                            warn!("PTY reader error: {e}");
                            let _ = tx.send(PtyEvent::Error(e.to_string()));
                            break;
                        }
                    }
                }
            })
            .expect("failed to spawn PTY reader thread");

        Self {
            writer,
            rx,
            _reader_thread: reader_thread,
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
}
