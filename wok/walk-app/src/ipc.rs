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
    /// Create a new pane. Direction is informational ("vertical", "horizontal").
    CreatePane {
        /// Split direction hint.
        direction: String,
    },
    /// Close an existing pane.
    ClosePane {
        /// Target pane id.
        pane_id: u64,
    },
    /// List all panes.
    GetPanes,
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
    /// Pane was created.
    PaneCreated {
        /// New pane id.
        pane_id: u64,
    },
    /// List of panes.
    Panes {
        /// Pane info items.
        items: Vec<PaneInfo>,
    },
}

/// Information about one pane.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaneInfo {
    /// Pane identifier.
    pub pane_id: u64,
    /// Column count.
    pub cols: u16,
    /// Row count.
    pub rows: u16,
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

    #[test]
    fn test_round_trip_create_pane() {
        let mut buffer = Vec::new();
        write_frame(
            &mut buffer,
            &ClientMessage::CreatePane {
                direction: "vertical".to_string(),
            },
        )
        .expect("frame should write");
        let mut cursor = std::io::Cursor::new(buffer);
        let msg: ClientMessage = read_frame(&mut cursor).expect("frame should read");
        match msg {
            ClientMessage::CreatePane { direction } => assert_eq!(direction, "vertical"),
            _ => panic!("expected CreatePane"),
        }
    }

    #[test]
    fn test_round_trip_close_pane() {
        let mut buffer = Vec::new();
        write_frame(
            &mut buffer,
            &ClientMessage::ClosePane { pane_id: 42 },
        )
        .expect("frame should write");
        let mut cursor = std::io::Cursor::new(buffer);
        let msg: ClientMessage = read_frame(&mut cursor).expect("frame should read");
        match msg {
            ClientMessage::ClosePane { pane_id } => assert_eq!(pane_id, 42),
            _ => panic!("expected ClosePane"),
        }
    }

    #[test]
    fn test_round_trip_get_panes() {
        let mut buffer = Vec::new();
        write_frame(&mut buffer, &ClientMessage::GetPanes).expect("frame should write");
        let mut cursor = std::io::Cursor::new(buffer);
        let msg: ClientMessage = read_frame(&mut cursor).expect("frame should read");
        assert!(matches!(msg, ClientMessage::GetPanes));
    }

    #[test]
    fn test_round_trip_pane_created() {
        let mut buffer = Vec::new();
        write_frame(
            &mut buffer,
            &ServerMessage::PaneCreated { pane_id: 7 },
        )
        .expect("frame should write");
        let mut cursor = std::io::Cursor::new(buffer);
        let msg: ServerMessage = read_frame(&mut cursor).expect("frame should read");
        match msg {
            ServerMessage::PaneCreated { pane_id } => assert_eq!(pane_id, 7),
            _ => panic!("expected PaneCreated"),
        }
    }

    #[test]
    fn test_round_trip_panes() {
        let items = vec![
            PaneInfo { pane_id: 0, cols: 80, rows: 24 },
            PaneInfo { pane_id: 1, cols: 40, rows: 24 },
        ];
        let mut buffer = Vec::new();
        write_frame(
            &mut buffer,
            &ServerMessage::Panes { items },
        )
        .expect("frame should write");
        let mut cursor = std::io::Cursor::new(buffer);
        let msg: ServerMessage = read_frame(&mut cursor).expect("frame should read");
        match msg {
            ServerMessage::Panes { items } => {
                assert_eq!(items.len(), 2);
                assert_eq!(items[0].pane_id, 0);
                assert_eq!(items[1].pane_id, 1);
                assert_eq!(items[1].cols, 40);
            }
            _ => panic!("expected Panes"),
        }
    }
}
