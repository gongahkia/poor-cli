//! URL detection and clickable links in terminal output.

use std::sync::OnceLock;

use crate::quick_select::{PatternRegistry, PatternType};

/// A detected URL span in a line of text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UrlSpan {
    /// Start column.
    pub col_start: u16,
    /// End column (exclusive).
    pub col_end: u16,
    /// The URL string.
    pub url: String,
}

/// Detect URLs in a line of text.
pub fn detect_urls(line_text: &str) -> Vec<UrlSpan> {
    static REGISTRY: OnceLock<PatternRegistry> = OnceLock::new();
    let registry = REGISTRY.get_or_init(PatternRegistry::new);
    registry
        .detect_line(0, line_text)
        .into_iter()
        .filter_map(|candidate| {
            matches!(candidate.pattern_type, PatternType::Url).then(|| UrlSpan {
                col_start: candidate.col_start as u16,
                col_end: candidate.col_end as u16,
                url: candidate.text,
            })
        })
        .collect()
}

/// Open a URL in the default browser.
pub fn open_url(url: &str) {
    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("open").arg(url).spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let _ = std::process::Command::new("xdg-open").arg(url).spawn();
    }
    #[cfg(target_os = "windows")]
    {
        let _ = std::process::Command::new("cmd")
            .args(["/c", "start", url])
            .spawn();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_url() {
        let urls = detect_urls("visit https://example.com today");
        assert_eq!(urls.len(), 1);
        assert_eq!(urls[0].url, "https://example.com");
    }

    #[test]
    fn test_detect_url_with_path() {
        let urls = detect_urls("see https://example.com/path?q=1#section");
        assert_eq!(urls.len(), 1);
        assert!(urls[0].url.contains("/path?q=1#section"));
    }

    #[test]
    fn test_no_url() {
        let urls = detect_urls("no urls here");
        assert!(urls.is_empty());
    }

    #[test]
    fn test_bare_protocol_ignored() {
        let urls = detect_urls("http:// alone");
        assert!(urls.is_empty()); // too short
    }
}
