/// Shared command helpers for the TUI library crate.
///
/// The binary's slash-command runtime currently lives in `src/commands.rs`.
pub fn normalize_slash_command(raw: &str) -> String {
    raw.trim().to_ascii_lowercase()
}
