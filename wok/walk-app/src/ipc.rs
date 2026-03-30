//! IPC protocol and framing for daemon/client communication.

use std::io::{Read, Write};

use serde::{Deserialize, Serialize};

/// Client-to-daemon messages.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ClientMessage {
    /// Request attach to a named session.
    Attach {
        /// Target session name.
        session: String,
    },
    /// Notify detach for a named session.
    Detach {
        /// Target session name.
        session: String,
    },
    /// Request session metadata.
    SessionState {
        /// Target session name.
        session: String,
    },
    /// Request daemon shutdown.
    Kill {
        /// Target session name.
        session: String,
    },
    /// Forward terminal input bytes.
    Input {
        /// Target pane id.
        pane_id: u64,
        /// Raw input bytes.
        data: Vec<u8>,
    },
    /// Resize a pane.
    Resize {
        /// Target pane id.
        pane_id: u64,
        /// New column count.
        cols: u16,
        /// New row count.
        rows: u16,
    },
    /// Request a full state snapshot.
    Snapshot,
}

/// Daemon-to-client messages.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ServerMessage {
    /// Acknowledge message.
    Ack,
    /// Error response.
    Error {
        /// Error details.
        message: String,
    },
    /// Session metadata reply.
    SessionState {
        /// Session name.
        session: String,
        /// Number of panes in session.
        pane_count: usize,
        /// Number of attached clients.
        attached_clients: usize,
        /// Running flag.
        running: bool,
    },
    /// Serialized workspace/session snapshot.
    Snapshot {
        /// Snapshot payload.
        payload: serde_json::Value,
    },
}

/// Write one length-prefixed JSON message.
pub fn write_frame<T>(writer: &mut impl Write, message: &T) -> Result<(), std::io::Error>
where
    T: Serialize,
{
    let payload = serde_json::to_vec(message).map_err(std::io::Error::other)?;
    let len = payload.len() as u32;
    writer.write_all(&len.to_be_bytes())?;
    writer.write_all(&payload)?;
    Ok(())
}

/// Read one length-prefixed JSON message.
pub fn read_frame<T>(reader: &mut impl Read) -> Result<T, std::io::Error>
where
    T: for<'de> Deserialize<'de>,
{
    let mut len_bytes = [0u8; 4];
    reader.read_exact(&mut len_bytes)?;
    let len = u32::from_be_bytes(len_bytes) as usize;
    let mut payload = vec![0u8; len];
    reader.read_exact(&mut payload)?;
    serde_json::from_slice(&payload).map_err(std::io::Error::other)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_round_trip_frame() {
        let mut buffer = Vec::new();
        write_frame(
            &mut buffer,
            &ClientMessage::Attach {
                session: "work".to_string(),
            },
        )
        .expect("frame should write");

        let mut cursor = std::io::Cursor::new(buffer);
        let message: ClientMessage = read_frame(&mut cursor).expect("frame should read");
        assert!(matches!(message, ClientMessage::Attach { .. }));
    }
}
