//! Wokcast — newline-delimited record format for raw PTY byte streams.
//!
//! Format (one line per record, ASCII):
//! ```text
//! # wokcast v1 cols=<cols> rows=<rows> started=<unix_secs>
//! <ts_us> <base64 chunk>
//! <ts_us> <base64 chunk>
//! ```
//!
//! `ts_us` is microseconds since session start (monotonic). Chunks are
//! arbitrary byte slices (terminal escape sequences included).
//!
//! Self-contained: no upload, no network. The companion replay APIs schedule
//! decoded chunks against a virtual terminal at original cadence (or a
//! configurable speed multiplier) — pure I/O over the file.

use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

/// Header captured at the top of a wokcast file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CastHeader {
    /// Terminal column count at recording time.
    pub cols: u16,
    /// Terminal row count at recording time.
    pub rows: u16,
    /// Unix epoch seconds when recording started.
    pub started_unix_secs: u64,
}

impl Default for CastHeader {
    fn default() -> Self {
        Self {
            cols: 80,
            rows: 24,
            started_unix_secs: 0,
        }
    }
}

/// Single decoded record.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CastRecord {
    /// Microseconds since recording start.
    pub elapsed_us: u64,
    /// Raw bytes (PTY output).
    pub bytes: Vec<u8>,
}

/// Streaming writer.
pub struct CastWriter<W: Write> {
    inner: W,
    header_written: bool,
    header: CastHeader,
}

impl<W: Write> CastWriter<W> {
    /// Build a writer over `inner` w/ given dims.
    pub fn new(inner: W, cols: u16, rows: u16) -> Self {
        Self {
            inner,
            header_written: false,
            header: CastHeader {
                cols,
                rows,
                started_unix_secs: SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map(|d| d.as_secs())
                    .unwrap_or(0),
            },
        }
    }

    /// Header that will be (or was) emitted.
    pub fn header(&self) -> CastHeader {
        self.header
    }

    fn write_header(&mut self) -> io::Result<()> {
        writeln!(
            self.inner,
            "# wokcast v1 cols={} rows={} started={}",
            self.header.cols, self.header.rows, self.header.started_unix_secs
        )?;
        self.header_written = true;
        Ok(())
    }

    /// Append one chunk. `elapsed_us` is monotonic since session start.
    pub fn write_chunk(&mut self, elapsed_us: u64, bytes: &[u8]) -> io::Result<()> {
        if !self.header_written {
            self.write_header()?;
        }
        let encoded = B64.encode(bytes);
        writeln!(self.inner, "{elapsed_us} {encoded}")?;
        Ok(())
    }

    /// Flush underlying writer.
    pub fn flush(&mut self) -> io::Result<()> {
        self.inner.flush()
    }
}

/// Streaming reader. Yields `CastRecord`s in stored order.
pub struct CastReader<R: Read> {
    inner: BufReader<R>,
    header: Option<CastHeader>,
    line_no: usize,
}

impl<R: Read> CastReader<R> {
    /// Build a reader over `inner`. Header is parsed lazily on first call.
    pub fn new(inner: R) -> Self {
        Self {
            inner: BufReader::new(inner),
            header: None,
            line_no: 0,
        }
    }

    /// Parse the header, if not already.
    pub fn header(&mut self) -> io::Result<CastHeader> {
        if let Some(h) = self.header {
            return Ok(h);
        }
        let mut line = String::new();
        let n = self.inner.read_line(&mut line)?;
        self.line_no += 1;
        if n == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "empty cast file",
            ));
        }
        let h = parse_header(line.trim_end_matches('\n'))?;
        self.header = Some(h);
        Ok(h)
    }

    /// Read next record. Returns `Ok(None)` at EOF.
    pub fn next_record(&mut self) -> io::Result<Option<CastRecord>> {
        if self.header.is_none() {
            let _ = self.header()?;
        }
        let mut line = String::new();
        loop {
            line.clear();
            let n = self.inner.read_line(&mut line)?;
            self.line_no += 1;
            if n == 0 {
                return Ok(None);
            }
            let trimmed = line.trim_end_matches(['\r', '\n']);
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }
            return parse_record(trimmed)
                .map(Some)
                .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e));
        }
    }
}

fn parse_header(line: &str) -> io::Result<CastHeader> {
    let prefix = "# wokcast v1 ";
    if !line.starts_with(prefix) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "missing wokcast v1 header",
        ));
    }
    let mut h = CastHeader::default();
    for part in line[prefix.len()..].split_whitespace() {
        if let Some((k, v)) = part.split_once('=') {
            match k {
                "cols" => {
                    h.cols = v
                        .parse()
                        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "bad cols"))?;
                }
                "rows" => {
                    h.rows = v
                        .parse()
                        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "bad rows"))?;
                }
                "started" => {
                    h.started_unix_secs = v
                        .parse()
                        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "bad started"))?;
                }
                _ => {} // forward-compat: ignore unknown keys
            }
        }
    }
    Ok(h)
}

fn parse_record(line: &str) -> Result<CastRecord, String> {
    let (ts, b64) = line.split_once(' ').ok_or("missing space separator")?;
    let elapsed_us: u64 = ts.parse().map_err(|_| "bad timestamp".to_string())?;
    let bytes = B64
        .decode(b64.as_bytes())
        .map_err(|e| format!("bad base64: {e}"))?;
    Ok(CastRecord { elapsed_us, bytes })
}

/// Replay scheduler — yields `(delay_until_next, bytes)` pairs from a reader.
///
/// `speed` scales playback time (1.0 = original, 2.0 = double-speed). Use
/// 0.0 to skip waits entirely (deterministic test playback).
pub fn schedule<R: Read>(
    reader: &mut CastReader<R>,
    speed: f64,
) -> io::Result<Vec<(Duration, Vec<u8>)>> {
    let mut out = Vec::new();
    let mut last_us: u64 = 0;
    while let Some(rec) = reader.next_record()? {
        let delta_us = rec.elapsed_us.saturating_sub(last_us);
        let scaled = if speed <= 0.0 {
            0
        } else {
            (delta_us as f64 / speed) as u64
        };
        out.push((Duration::from_micros(scaled), rec.bytes));
        last_us = rec.elapsed_us;
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn round_trip_writes_and_reads() {
        let mut buf = Vec::new();
        {
            let mut w = CastWriter::new(&mut buf, 80, 24);
            w.write_chunk(0, b"hello").unwrap();
            w.write_chunk(1500, b"\x1b[31mred\x1b[0m").unwrap();
            w.write_chunk(2_000_000, b"world").unwrap();
            w.flush().unwrap();
        }
        let mut r = CastReader::new(Cursor::new(&buf));
        let h = r.header().unwrap();
        assert_eq!(h.cols, 80);
        assert_eq!(h.rows, 24);

        let r1 = r.next_record().unwrap().unwrap();
        assert_eq!(r1.elapsed_us, 0);
        assert_eq!(r1.bytes, b"hello");

        let r2 = r.next_record().unwrap().unwrap();
        assert_eq!(r2.elapsed_us, 1500);
        assert_eq!(r2.bytes, b"\x1b[31mred\x1b[0m");

        let r3 = r.next_record().unwrap().unwrap();
        assert_eq!(r3.elapsed_us, 2_000_000);
        assert_eq!(r3.bytes, b"world");

        assert!(r.next_record().unwrap().is_none());
    }

    #[test]
    fn missing_header_errors() {
        let buf = b"0 aGk=\n";
        let mut r = CastReader::new(Cursor::new(buf));
        assert!(r.header().is_err());
    }

    #[test]
    fn schedule_yields_relative_durations() {
        let mut buf = Vec::new();
        {
            let mut w = CastWriter::new(&mut buf, 80, 24);
            w.write_chunk(0, b"a").unwrap();
            w.write_chunk(500_000, b"b").unwrap();
            w.write_chunk(1_500_000, b"c").unwrap();
        }
        let mut r = CastReader::new(Cursor::new(&buf));
        let plan = schedule(&mut r, 1.0).unwrap();
        assert_eq!(plan.len(), 3);
        assert_eq!(plan[0].0, Duration::from_micros(0));
        assert_eq!(plan[0].1, b"a");
        assert_eq!(plan[1].0, Duration::from_micros(500_000));
        assert_eq!(plan[2].0, Duration::from_micros(1_000_000));
    }

    #[test]
    fn schedule_speed_scales_durations() {
        let mut buf = Vec::new();
        {
            let mut w = CastWriter::new(&mut buf, 80, 24);
            w.write_chunk(0, b"a").unwrap();
            w.write_chunk(1_000_000, b"b").unwrap();
        }
        let mut r = CastReader::new(Cursor::new(&buf));
        let plan = schedule(&mut r, 2.0).unwrap();
        assert_eq!(plan[1].0, Duration::from_micros(500_000));
    }

    #[test]
    fn schedule_speed_zero_collapses_to_instant() {
        let mut buf = Vec::new();
        {
            let mut w = CastWriter::new(&mut buf, 80, 24);
            w.write_chunk(0, b"a").unwrap();
            w.write_chunk(1_000_000, b"b").unwrap();
        }
        let mut r = CastReader::new(Cursor::new(&buf));
        let plan = schedule(&mut r, 0.0).unwrap();
        assert!(plan.iter().all(|(d, _)| d.is_zero()));
    }

    #[test]
    fn comment_and_blank_lines_skipped() {
        let payload =
            b"# wokcast v1 cols=80 rows=24 started=0\n# extra\n\n0 aGk=\n# more\n10 d29ya2Vk\n";
        let mut r = CastReader::new(Cursor::new(payload));
        let r1 = r.next_record().unwrap().unwrap();
        assert_eq!(r1.bytes, b"hi");
        let r2 = r.next_record().unwrap().unwrap();
        assert_eq!(r2.bytes, b"worked");
        assert!(r.next_record().unwrap().is_none());
    }

    #[test]
    fn malformed_record_errors_on_read() {
        let payload = b"# wokcast v1 cols=80 rows=24 started=0\nNOTANUMBER aGk=\n";
        let mut r = CastReader::new(Cursor::new(payload));
        let err = r.next_record().unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn header_round_trips_unknown_keys_ignored() {
        let payload = b"# wokcast v1 cols=132 rows=43 started=42 newkey=foo\n0 aGk=\n";
        let mut r = CastReader::new(Cursor::new(payload));
        let h = r.header().unwrap();
        assert_eq!(h.cols, 132);
        assert_eq!(h.rows, 43);
        assert_eq!(h.started_unix_secs, 42);
    }
}
