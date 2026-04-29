//! Block export to plain markdown.
//!
//! Local-first equivalent of warp's "share block" modal: serialise a single
//! block (cmd, exit, cwd, output, duration) to a self-contained `.md` file.
//! No upload path; caller decides where bytes land.
//!
//! The Block record carries metadata but not output text (output lives in the
//! terminal grid keyed by `output_start_row..=output_end_row`). This module
//! takes the output lines as a separate argument so it stays pure and can be
//! exercised without a live terminal.

use std::time::Duration;

use crate::block::Block;

/// Output mode for [`format_markdown`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputMode {
    /// Strip CSI/SGR escape sequences before emitting in a fenced block.
    Plain,
    /// Preserve raw bytes (caller may have already stripped); emit as-is.
    Ansi,
}

/// Render `block` + `output_lines` as a markdown document.
pub fn format_markdown(block: &Block, output_lines: &[String], mode: OutputMode) -> String {
    let mut s = String::new();
    s.push_str("# Block ");
    s.push_str(&block.id.to_string());
    s.push_str("\n\n");

    s.push_str("- **cwd:** `");
    s.push_str(&block.cwd.display().to_string());
    s.push_str("`\n");

    if let Some(branch) = &block.git_branch {
        s.push_str("- **git:** `");
        s.push_str(branch);
        if matches!(block.git_dirty, Some(true)) {
            s.push('*');
        }
        s.push_str("`\n");
    }

    match block.exit_code {
        Some(0) => s.push_str("- **exit:** 0\n"),
        Some(c) => {
            s.push_str("- **exit:** ");
            s.push_str(&c.to_string());
            s.push_str(" (failed)\n");
        }
        None => s.push_str("- **exit:** _(running)_\n"),
    }

    if let Some(d) = block.duration {
        s.push_str("- **duration:** ");
        s.push_str(&format_duration(d));
        s.push('\n');
    }

    s.push_str("\n## Command\n\n```sh\n");
    s.push_str(block.command_text.trim_end_matches('\n'));
    s.push_str("\n```\n\n");

    s.push_str("## Output\n\n");
    let fence = if mode == OutputMode::Ansi {
        "```ansi"
    } else {
        "```text"
    };
    s.push_str(fence);
    s.push('\n');
    for line in output_lines {
        let rendered = match mode {
            OutputMode::Plain => strip_csi(line),
            OutputMode::Ansi => line.clone(),
        };
        s.push_str(&rendered);
        if !rendered.ends_with('\n') {
            s.push('\n');
        }
    }
    s.push_str("```\n");
    s
}

/// Best-effort CSI/SGR stripper. Removes `ESC [ ... letter` and `ESC ] ... BEL`
/// runs. Bare `ESC` not followed by a recognised intro is kept as-is.
pub fn strip_csi(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    let bytes = input.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let b = bytes[i];
        if b == 0x1b && i + 1 < bytes.len() {
            let n = bytes[i + 1];
            if n == b'[' {
                // CSI: read until final byte in 0x40..=0x7e
                let mut j = i + 2;
                while j < bytes.len() && !(0x40..=0x7e).contains(&bytes[j]) {
                    j += 1;
                }
                i = j.saturating_add(1);
                continue;
            }
            if n == b']' {
                // OSC: read until BEL or ESC \
                let mut j = i + 2;
                while j < bytes.len() {
                    if bytes[j] == 0x07 {
                        j += 1;
                        break;
                    }
                    if bytes[j] == 0x1b && j + 1 < bytes.len() && bytes[j + 1] == b'\\' {
                        j += 2;
                        break;
                    }
                    j += 1;
                }
                i = j;
                continue;
            }
        }
        // safe: writes one byte at a time but only ASCII paths above; for non-ASCII just copy.
        out.push(input[i..].chars().next().unwrap());
        i += input[i..].chars().next().unwrap().len_utf8();
    }
    out
}

fn format_duration(d: Duration) -> String {
    let total_ms = d.as_millis();
    if total_ms < 1000 {
        format!("{total_ms}ms")
    } else if total_ms < 60_000 {
        format!("{:.2}s", d.as_secs_f64())
    } else {
        let secs = d.as_secs();
        format!("{}m{}s", secs / 60, secs % 60)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::time::{Duration, Instant};

    fn sample_block() -> Block {
        Block {
            id: 7,
            prompt_text: "$ ".into(),
            command_text: "echo hi".into(),
            output_start_row: 10,
            output_end_row: 11,
            exit_code: Some(0),
            start_time: Instant::now(),
            end_time: None,
            duration: Some(Duration::from_millis(42)),
            is_collapsed: false,
            scroll_offset: 0,
            cwd: PathBuf::from("/tmp/work"),
            git_branch: Some("main".into()),
            git_dirty: Some(false),
            is_bookmarked: false,
            trigger_highlights: Vec::new(),
        }
    }

    #[test]
    fn markdown_contains_metadata_and_command() {
        let b = sample_block();
        let md = format_markdown(&b, &["hi".into()], OutputMode::Plain);
        assert!(md.contains("# Block 7"));
        assert!(md.contains("**cwd:** `/tmp/work`"));
        assert!(md.contains("**git:** `main`"));
        assert!(md.contains("**exit:** 0"));
        assert!(md.contains("**duration:** 42ms"));
        assert!(md.contains("```sh\necho hi\n```"));
        assert!(md.contains("```text\nhi\n```"));
    }

    #[test]
    fn dirty_branch_marker() {
        let mut b = sample_block();
        b.git_dirty = Some(true);
        let md = format_markdown(&b, &[], OutputMode::Plain);
        assert!(md.contains("**git:** `main*`"));
    }

    #[test]
    fn nonzero_exit_marked_failed() {
        let mut b = sample_block();
        b.exit_code = Some(2);
        let md = format_markdown(&b, &[], OutputMode::Plain);
        assert!(md.contains("**exit:** 2 (failed)"));
    }

    #[test]
    fn running_block_renders_marker() {
        let mut b = sample_block();
        b.exit_code = None;
        let md = format_markdown(&b, &[], OutputMode::Plain);
        assert!(md.contains("**exit:** _(running)_"));
    }

    #[test]
    fn ansi_mode_uses_ansi_fence_and_keeps_bytes() {
        let b = sample_block();
        let md = format_markdown(&b, &["\x1b[31mred\x1b[0m".into()], OutputMode::Ansi);
        assert!(md.contains("```ansi"));
        assert!(md.contains("\x1b[31mred"));
    }

    #[test]
    fn plain_mode_strips_csi() {
        let b = sample_block();
        let md = format_markdown(&b, &["\x1b[31mred\x1b[0m text".into()], OutputMode::Plain);
        assert!(!md.contains("\x1b["));
        assert!(md.contains("red text"));
    }

    #[test]
    fn strip_csi_handles_osc_with_bel() {
        let s = strip_csi("\x1b]0;title\x07hello");
        assert_eq!(s, "hello");
    }

    #[test]
    fn strip_csi_handles_osc_with_st() {
        let s = strip_csi("\x1b]8;;https://x\x1b\\link");
        assert_eq!(s, "link");
    }

    #[test]
    fn duration_formatting() {
        assert_eq!(format_duration(Duration::from_millis(7)), "7ms");
        assert_eq!(format_duration(Duration::from_millis(1500)), "1.50s");
        assert_eq!(format_duration(Duration::from_secs(125)), "2m5s");
    }
}
